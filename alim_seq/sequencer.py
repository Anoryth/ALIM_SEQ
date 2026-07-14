"""Sequencer: parses and runs a sequence file.

File format: **one action per line**. Empty lines and those starting with ``#``
(or ``//``) are ignored. Keywords are case-insensitive; channel *labels* and
sensor names respect the configuration's case.

Available commands
-------------------
    SET <channel> <voltage_V> [current_A]  Sets the voltage (and current limit).
    VOLTAGE <channel> <voltage_V>          Sets the voltage only.
    CURRENT <channel> <current_A>          Sets the current limit only.
    SETV <channel> = <expression>          Sets the voltage from a formula
                                         (e.g. SETV VG2 = (VD/2)+VG1). A bare
                                         channel name = its voltage setpoint;
                                         functions V(x), Vmeas(x), Iset(x), I(x)
                                         available.
    SETI <channel> = <expression>          Same for the current limit.
    ON <channel>                           Switches the channel on.
    OFF <channel>                          Switches the channel off.
    WAIT <seconds>                         Pause (interruptible).
    RAMP <channel> <v_end> <duration_s>                Ramp FROM the channel's
                                         current value to <v_end>.
    RAMP <channel> <v_start> <v_end> <duration_s> [steps]  Ramp with explicit
                                         start. [steps] = NUMBER of steps
                                         (integer >= 2), not a step size.
    SERVO_LIN <set_channel> <measured_channel> <target_current_A> [key=value ...]
                                         Servos the voltage of <set_channel>
                                         until the target current is reached on
                                         <measured_channel>, at a FIXED STEP
                                         (|step| per iteration). Keys: step, min,
                                         max, tol, timeout, settle, invert.
                                         ('SERVO' = alias for SERVO_LIN.)
    SERVO_ADAPT <set_channel> <measured_channel> <target_current_A> [key=value ...]
                                         Same but with an ADAPTIVE STEP
                                         (secant/Newton: measured slope dI/dV ->
                                         large far, fine near). 'step' becomes a
                                         CEILING. Extra key: damping (default 0.7).
    WAIT_CURRENT <channel> <op> <value> [timeout=<s>]  Waits for a current
                                         condition.
    WAIT_TEMP <sensor> <op> <value> [timeout=<s>]      Waits for a temperature
                                         condition.
                                         op ∈ { < <= > >= == != }
    LOG <message...>                       Writes a message to the log.
    ALL_OFF                                Switches off all channels.
    RELAY <output> ON|OFF                  Closes (ON) / opens (OFF) a relay
                                         output.
    REPEAT <n>  …  END                     Repeats the block n times (nesting OK).

Example
-------
    # Power-up
    SET VCC 3.3 1.0
    ON VCC
    WAIT 1.0
    SERVO_ADAPT VBIAS VCC 0.5 step=0.5 max=5.0 tol=0.005
    WAIT 2
    ALL_OFF
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Optional, Set

from .expressions import ExprError, references
from .i18n import _

if TYPE_CHECKING:  # avoids an import cycle (controller imports sequencer)
    from .controller import Controller

_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: abs(a - b) < 1e-9,
    "!=": lambda a, b: abs(a - b) >= 1e-9,
}


class SequenceError(Exception):
    """Syntax/validation error in the sequence file."""


@dataclass
class Action:
    """A parsed sequence action.

    ``lineno`` = source line (kept after loop expansion, for the editor's
    highlighting); ``cmd`` = UPPERCASE keyword; ``args`` = the raw arguments
    (str, converted at execution time); ``raw`` = the original line (shown in
    the log)."""
    lineno: int
    cmd: str
    args: List[str]
    raw: str


# --------------------------------------------------------------------- parser
def parse_sequence(
    text: str,
    valid_labels: Set[str],
    valid_sensors: Set[str],
    valid_relays: Set[str] = frozenset(),
) -> List[Action]:
    """Parses a sequence's text and validates the references (channels/sensors/relays)."""
    actions: List[Action] = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        # Strips an optional trailing comment.
        for marker in ("#", "//"):
            if marker in stripped and not stripped.upper().startswith("LOG"):
                stripped = stripped.split(marker, 1)[0].strip()
        parts = stripped.split()
        cmd = parts[0].upper()
        args = parts[1:]
        action = Action(lineno=i, cmd=cmd, args=args, raw=line.strip())
        _validate_action(action, valid_labels, valid_sensors, valid_relays)
        actions.append(action)
    return _expand_loops(actions)


def _expand_loops(actions: List[Action]) -> List[Action]:
    """Unrolls ``REPEAT n … END`` blocks (nesting handled) into a flat list.

    The actions keep their source ``lineno`` (the editor's highlighting stays
    correct). Guard against a runaway expansion.
    """
    stack: List[List[Action]] = [[]]
    counts: List[int] = []
    for a in actions:
        if a.cmd == "REPEAT":
            stack.append([])
            counts.append(int(a.args[0]))
        elif a.cmd == "END":
            if len(stack) == 1:
                raise SequenceError(_("Line {}: 'END' without matching 'REPEAT'.").format(a.lineno))
            block, n = stack.pop(), counts.pop()
            stack[-1].extend(block * n)
            if len(stack[-1]) > 200000:
                raise SequenceError(_("Sequence too long after loop expansion "
                                      "(REPEAT too large)."))
        else:
            stack[-1].append(a)
    if len(stack) != 1:
        raise SequenceError(_("'REPEAT' without matching 'END'."))
    return stack[0]


def estimate_duration(actions: List[Action]) -> float:
    """Estimated minimum duration (s): sum of the WAIT/DELAY and RAMP durations.

    SERVO / WAIT_CURRENT / WAIT_TEMP (unbounded duration) are not counted."""
    total = 0.0
    for a in actions:
        try:
            if a.cmd in ("WAIT", "DELAY"):
                total += float(a.args[0])
            elif a.cmd == "RAMP":
                total += float(a.args[3] if len(a.args) >= 4 else a.args[2])
        except (IndexError, ValueError):
            pass
    return total


def _need(action: Action, n: int) -> None:
    if len(action.args) < n:
        raise SequenceError(
            _("Line {}: '{}' expects at least {} argument(s) -> {!r}").format(
                action.lineno, action.cmd, n, action.raw)
        )


def _check_label(action: Action, label: str, valid_labels: Set[str]) -> None:
    if label not in valid_labels:
        raise SequenceError(
            _("Line {}: unknown channel {!r}. Valid channels: {}").format(
                action.lineno, label, sorted(valid_labels))
        )


# Allowed keys for the key=value arguments of servos and waits.
_SERVO_KEYS: Set[str] = {"step", "min", "max", "tol", "timeout", "settle", "invert"}
_SERVO_ADAPT_KEYS: Set[str] = _SERVO_KEYS | {"damping"}
_WAIT_KEYS: Set[str] = {"timeout"}


def _ramp_steps(action: Action, raw: str) -> int:
    """Validates RAMP's optional ``[steps]`` argument: it is a NUMBER OF STEPS,
    hence an integer >= 2 (``0.1`` is refused: it is not a step size)."""
    try:
        n = int(raw)
    except ValueError:
        raise SequenceError(
            _("Line {}: RAMP [steps] is the number of steps (integer >= 2), "
              "got {!r} -> {!r}").format(action.lineno, raw, action.raw))
    if n < 2:
        raise SequenceError(
            _("Line {}: RAMP [steps] (number of steps) must be >= 2 (got {}).").format(
                action.lineno, n))
    return n


def _num(action: Action, idx: int, name: str, *, non_neg: bool = False,
         positive: bool = False) -> float:
    """Converts ``args[idx]`` to float, otherwise raises an explicit SequenceError."""
    try:
        v = float(action.args[idx])
    except (IndexError, ValueError):
        raise SequenceError(
            _("Line {}: '{}' expects a number for {} -> {!r}").format(
                action.lineno, action.cmd, name, action.raw))
    if positive and not v > 0:
        raise SequenceError(
            _("Line {}: {} must be > 0 (got {}).").format(action.lineno, name, v))
    if non_neg and v < 0:
        raise SequenceError(
            _("Line {}: {} must be >= 0 (got {}).").format(action.lineno, name, v))
    return v


def _check_kwargs(action: Action, start: int, allowed: Set[str]) -> None:
    """Validates ``key=value`` arguments: correct form, known key, numeric
    value. Any key outside the whitelist is rejected at parse time."""
    for a in action.args[start:]:
        if "=" not in a:
            raise SequenceError(
                _("Line {}: '{}' expects key=value pairs, got {!r} -> {!r}").format(
                    action.lineno, action.cmd, a, action.raw))
        k, v = a.split("=", 1)
        key = k.strip().lower()
        if key not in allowed:
            raise SequenceError(
                _("Line {}: unknown key {!r} for '{}'. Valid keys: {}").format(
                    action.lineno, key, action.cmd, sorted(allowed)))
        try:
            float(v)
        except ValueError:
            raise SequenceError(
                _("Line {}: non-numeric value for {!r}: {!r}").format(action.lineno, key, v))


def _validate_action(action: Action, valid_labels: Set[str], valid_sensors: Set[str],
                     valid_relays: Set[str] = frozenset()) -> None:
    c = action.cmd
    if c == "SET":
        _need(action, 2)
        _check_label(action, action.args[0], valid_labels)
        _num(action, 1, _("voltage"))
        if len(action.args) >= 3:
            _num(action, 2, _("current"), non_neg=True)
    elif c in ("VOLTAGE", "VOLT"):
        _need(action, 2)
        _check_label(action, action.args[0], valid_labels)
        _num(action, 1, _("voltage"))
    elif c in ("CURRENT", "CURR"):
        _need(action, 2)
        _check_label(action, action.args[0], valid_labels)
        _num(action, 1, _("current"), non_neg=True)
    elif c in ("ON", "OFF"):
        _need(action, 1)
        _check_label(action, action.args[0], valid_labels)
    elif c in ("WAIT", "DELAY"):
        _need(action, 1)
        _num(action, 0, _("duration"), non_neg=True)
    elif c == "RAMP":
        # 2 forms: "RAMP <channel> <v_end> <duration>" (start = current value)
        #       or "RAMP <channel> <v_start> <v_end> <duration> [steps]".
        _need(action, 3)
        _check_label(action, action.args[0], valid_labels)
        if len(action.args) >= 4:
            _num(action, 1, _("start voltage"))
            _num(action, 2, _("final voltage"))
            _num(action, 3, _("duration"), positive=True)
            if len(action.args) >= 5:
                _ramp_steps(action, action.args[4])
        else:
            _num(action, 1, _("final voltage"))
            _num(action, 2, _("duration"), positive=True)
    elif c in ("SERVO", "SERVO_LIN", "SERVO_ADAPT"):
        _need(action, 3)
        _check_label(action, action.args[0], valid_labels)
        _check_label(action, action.args[1], valid_labels)
        _num(action, 2, _("target current"))
        allowed = _SERVO_ADAPT_KEYS if c == "SERVO_ADAPT" else _SERVO_KEYS
        _check_kwargs(action, 3, allowed)
    elif c == "WAIT_CURRENT":
        _need(action, 3)
        _check_label(action, action.args[0], valid_labels)
        if action.args[1] not in _OPS:
            raise SequenceError(_("Line {}: invalid operator {!r}").format(action.lineno, action.args[1]))
        _num(action, 2, _("value"))
        _check_kwargs(action, 3, _WAIT_KEYS)
    elif c == "WAIT_TEMP":
        _need(action, 3)
        if action.args[0] not in valid_sensors:
            raise SequenceError(
                _("Line {}: unknown sensor {!r}. Sensors: {}").format(
                    action.lineno, action.args[0], sorted(valid_sensors))
            )
        if action.args[1] not in _OPS:
            raise SequenceError(_("Line {}: invalid operator {!r}").format(action.lineno, action.args[1]))
        _num(action, 2, _("value"))
        _check_kwargs(action, 3, _WAIT_KEYS)
    elif c in ("SETV", "SETI"):
        _need(action, 2)
        _check_label(action, action.args[0], valid_labels)
        expr = _expr_from_args(action.args[1:])
        try:
            refs = references(expr)
        except ExprError as exc:
            raise SequenceError(_("Line {}: {}").format(action.lineno, exc)) from exc
        for r in refs:
            if r not in valid_labels:
                raise SequenceError(
                    _("Line {}: unknown channel {!r} in expression. Valid channels: {}").format(
                        action.lineno, r, sorted(valid_labels))
                )
    elif c == "REPEAT":
        _need(action, 1)
        try:
            n = int(action.args[0])
        except ValueError:
            raise SequenceError(
                _("Line {}: 'REPEAT' expects an integer -> {!r}").format(action.lineno, action.raw))
        if n < 1:
            raise SequenceError(_("Line {}: 'REPEAT' must be >= 1.").format(action.lineno))
    elif c == "RELAY":
        _need(action, 2)
        if action.args[0] not in valid_relays:
            raise SequenceError(
                _("Line {}: unknown relay output {!r}. Outputs: {}").format(
                    action.lineno, action.args[0], sorted(valid_relays))
            )
        if action.args[1].upper() not in ("ON", "OFF"):
            raise SequenceError(
                _("Line {}: 'RELAY' expects ON or OFF -> {!r}").format(action.lineno, action.raw))
    elif c == "END":
        pass
    elif c in ("LOG", "ALL_OFF", "SHUTDOWN"):
        pass
    else:
        raise SequenceError(_("Line {}: unknown command {!r} -> {!r}").format(action.lineno, c, action.raw))


def _expr_from_args(args: List[str]) -> str:
    """Reconstructs the expression from the arguments (an optional leading '='
    is ignored: ``SETV VG2 = (VD/2)+VG1``)."""
    expr = " ".join(args).strip()
    if expr.startswith("="):
        expr = expr[1:].strip()
    return expr


def _kwargs(args: List[str]) -> dict:
    """Extracts the key=value pairs from an argument list (numeric values).

    Defensive: a non-numeric value raises a ``SequenceError`` (the keys are
    already validated at parse time by :func:`_check_kwargs`)."""
    out = {}
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            try:
                out[k.strip().lower()] = float(v)
            except ValueError:
                raise SequenceError(_("Non-numeric value for {!r}: {!r}").format(k.strip(), v))
    return out


# --------------------------------------------------------------------- runner
class SequenceRunner:
    """Runs a list of actions in a dedicated thread, interruptibly."""

    def __init__(self, controller: "Controller"):
        self.ctrl = controller
        self._thread: Optional[threading.Thread] = None
        # Two distinct stop intents:
        #  - _user_stop: stop requested by the operator (Stop button). REFUSED
        #    during a safety power-down (otherwise channels would stay powered).
        #  - _stop     : UNCONDITIONAL stop (force_stop), internal use (app
        #    shutdown, hard cut-off), which interrupts even a safety power-down.
        self._stop = threading.Event()
        self._user_stop = threading.Event()
        self._pause = threading.Event()  # set = execution paused
        # Serializes start(): closes the TOCTOU window between testing _running
        # and starting the thread (two concurrent start() -> a single sequence).
        self._start_lock = threading.Lock()
        self._running = False
        # safety_mode: power-down sequence launched by safety. It must run EVEN
        # when the safety lock is armed (tripped); it therefore only listens to
        # its own _stop, not abort_event/tripped.
        self._safety_mode = False
        # Progress (current action index, total) — simple attributes read by
        # the GUI via its timer, same model as the rest.
        self.progress = (0, 0)
        # Step-by-step mode: execution waits on step_event before EVERY action
        # (except during a safety power-down, which must never be blocked).
        self.step_mode = False
        self.step_event = threading.Event()
        self.on_line: Optional[Callable[[int, str], None]] = None
        self.on_finish: Optional[Callable[[bool, str], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def set_step_mode(self, on: bool) -> None:
        """Enables/disables step-by-step. Disabling it releases any pending wait
        (execution resumes continuously)."""
        self.step_mode = bool(on)
        if not on:
            self.step_event.set()

    def step_once(self) -> None:
        """Allows the next pending action to run (step-by-step)."""
        self.step_event.set()

    def start(self, actions: List[Action], safety_mode: bool = False) -> None:
        """Starts running ``actions`` in a dedicated thread.

        ``safety_mode=True`` marks a safety power-down: it runs even with the
        safety lock armed, ignores the user stop and the pause, and does not
        reset ``abort_event``. Raises ``RuntimeError`` if a sequence is already
        running."""
        # Lock: the test-then-arm of _running must be atomic.
        with self._start_lock:
            if self._running:
                raise RuntimeError(_("A sequence is already running."))
            self._running = True
        self._stop.clear()
        self._user_stop.clear()
        self._pause.clear()
        self.step_event.clear()
        self.progress = (0, len(actions))
        self._safety_mode = safety_mode
        if not safety_mode:
            self.ctrl.abort_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(actions,), name="sequence", daemon=True
        )
        self._thread.start()

    def stop(self) -> bool:
        """Stop requested by the OPERATOR (interrupts WAIT/SERVO). REFUSED during a
        safety power-down. Returns True if honored, False if refused."""
        if self._safety_mode:
            return False
        self._user_stop.set()
        self.ctrl.abort_event.set()
        return True

    def force_stop(self) -> None:
        """UNCONDITIONAL stop (internal use: app shutdown, hard cut-off).
        Interrupts even a safety power-down."""
        self._stop.set()
        self.ctrl.abort_event.set()

    def pause(self) -> None:
        if not self._safety_mode:   # a safety power-down cannot be paused
            self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    @property
    def is_paused(self) -> bool:
        return self._pause.is_set()

    def _paused(self) -> bool:
        return self._pause.is_set() and not self._safety_mode

    def _aborted(self) -> bool:
        """Should execution be interrupted? In safety mode, ONLY ``force_stop``
        (``_stop``) counts: neither the user stop, nor the armed lock, nor
        ``abort_event`` must stop a running power-down. Otherwise, any of these
        signals aborts the user sequence."""
        if self._safety_mode:
            # A safety power-down listens ONLY to force_stop (_stop), never the
            # user stop nor the lock: it must run the switch-off to completion.
            return self._stop.is_set()
        return (self._stop.is_set() or self._user_stop.is_set()
                or self.ctrl.abort_event.is_set() or self.ctrl.tripped)

    def _sleep(self, seconds: float) -> bool:
        """Interruptible (and pausable) sleep. Returns False if interrupted.
        The countdown is frozen while the sequence is paused."""
        remaining = seconds
        last = time.monotonic()
        while remaining > 0:
            if self._aborted():
                return False
            now = time.monotonic()
            if not self._paused():
                remaining -= now - last
            last = now
            time.sleep(0.05)
        return not self._aborted()

    def _run(self, actions: List[Action]) -> None:
        """Execution thread body: walks the actions one by one.

        Handles the pause, the abort and the step-by-step mode on each round,
        highlights the current line (``on_line``), logs, then delegates to
        :meth:`_execute`. Exits on the first failure/interruption. The
        ``finally`` block resets ``_running`` to False, adjusts the outcome if
        safety decided, and notifies ``on_finish(ok, message)``."""
        ok = True
        message = _("Sequence completed.")
        total = len(actions)
        try:
            for idx, action in enumerate(actions):
                self.progress = (idx, total)
                while self._paused() and not self._aborted():
                    time.sleep(0.05)   # suspended between two actions
                if self._aborted():
                    ok = False
                    message = _("Sequence interrupted.")
                    break
                # Highlights the NEXT action BEFORE the step-by-step wait.
                if self.on_line:
                    self.on_line(action.lineno, action.raw)
                # Step-by-step: waits for authorization (never during a safety power-down).
                if self.step_mode and not self._safety_mode:
                    self.step_event.clear()
                    while not self.step_event.is_set():
                        if self._aborted():
                            break
                        time.sleep(0.05)
                    self.step_event.clear()
                    if self._aborted():
                        ok = False
                        message = _("Sequence interrupted.")
                        break
                self.ctrl.log(f"> L{action.lineno}: {action.raw}")
                if not self._execute(action):
                    ok = False
                    message = _("Failure/interruption at line {}.").format(action.lineno)
                    break
            else:
                self.progress = (total, total)
        except Exception as exc:
            ok = False
            message = _("Line error: {}").format(exc)
            self.ctrl.log(_("Sequence error: {}").format(exc))
        finally:
            self._running = False
            if self.ctrl.tripped and not self._safety_mode:
                ok = False
                message = _("Sequence aborted by safety.")
            self.ctrl.log(message)
            if self.on_finish:
                self.on_finish(ok, message)

    def _execute(self, action: Action) -> bool:
        """Executes ONE action by routing it to the matching controller primitive.

        Returns True if the action succeeded and execution can continue, False
        on failure or interruption (WAIT/RAMP/SERVO/WAIT_* return False if
        aborted). Values are already validated at parse time: arguments can be
        converted without re-checking."""
        c = action.cmd
        a = action.args
        if c == "SET":
            self.ctrl.set_voltage(a[0], float(a[1]))
            if len(a) >= 3:
                self.ctrl.set_current(a[0], float(a[2]))
            return True
        if c in ("VOLTAGE", "VOLT"):
            self.ctrl.set_voltage(a[0], float(a[1]))
            return True
        if c in ("CURRENT", "CURR"):
            self.ctrl.set_current(a[0], float(a[1]))
            return True
        if c == "SETV":
            expr = _expr_from_args(a[1:])
            value = self.ctrl.eval_expression(expr)
            self.ctrl.set_voltage(a[0], value)
            self.ctrl.log(f"SETV {a[0]} = {expr} = {value:.4f} V")
            return True
        if c == "SETI":
            expr = _expr_from_args(a[1:])
            value = self.ctrl.eval_expression(expr)
            self.ctrl.set_current(a[0], value)
            self.ctrl.log(f"SETI {a[0]} = {expr} = {value:.4f} A")
            return True
        if c == "ON":
            self.ctrl.set_output(a[0], True)
            return True
        if c == "OFF":
            self.ctrl.set_output(a[0], False)
            return True
        if c in ("WAIT", "DELAY"):
            return self._sleep(float(a[0]))
        if c == "RAMP":
            return self._ramp(a)
        if c in ("SERVO", "SERVO_LIN"):  # 'SERVO' = backward-compatible alias
            kw = _kwargs(a[3:])
            return self.ctrl.servo(
                adjust_label=a[0],
                measure_label=a[1],
                target_current=float(a[2]),
                step=kw.get("step", 0.02),
                v_min=kw.get("min"),
                v_max=kw.get("max"),
                tol=kw.get("tol", 0.01),
                timeout=kw.get("timeout", 30.0),
                settle=kw.get("settle", 0.3),
                invert=bool(kw.get("invert", 0.0)),
                should_abort=self._aborted,
            )
        if c == "SERVO_ADAPT":
            kw = _kwargs(a[3:])
            return self.ctrl.servo_adaptive(
                adjust_label=a[0],
                measure_label=a[1],
                target_current=float(a[2]),
                step=kw.get("step", 0.5),
                v_min=kw.get("min"),
                v_max=kw.get("max"),
                tol=kw.get("tol", 0.01),
                timeout=kw.get("timeout", 30.0),
                settle=kw.get("settle", 0.3),
                invert=bool(kw.get("invert", 0.0)),
                damping=kw.get("damping", 0.7),
                should_abort=self._aborted,
            )
        if c == "WAIT_CURRENT":
            return self._wait_current(a)
        if c == "WAIT_TEMP":
            return self._wait_temp(a)
        if c == "LOG":
            self.ctrl.log("SEQ: " + " ".join(a))
            return True
        if c in ("ALL_OFF", "SHUTDOWN"):
            for label in self.ctrl.cfg.channels:
                self.ctrl.set_output(label, False)
            return True
        if c == "RELAY":
            self.ctrl.set_relay(a[0], a[1].upper() == "ON")
            return True
        return False

    def _ramp(self, a: List[str]) -> bool:
        """Runs a linear, step-wise voltage ramp (interruptible).

        Two forms (see the RAMP grammar): without a start voltage, starts from
        the channel's CURRENT setpoint; otherwise an explicit start with an
        optional number of steps. Duration <= 0 -> the final value is applied
        directly. Returns False if the ramp is aborted mid-way."""
        label = a[0]
        if len(a) == 3:
            # RAMP <channel> <v_end> <duration>: start = channel's CURRENT setpoint.
            v0 = self.ctrl.get_setpoint(label).set_voltage
            v1, duration = float(a[1]), float(a[2])
            steps = max(2, int(duration / 0.1))
        else:
            # RAMP <channel> <v_start> <v_end> <duration> [steps]: [steps] = NUMBER of steps.
            v0, v1, duration = float(a[1]), float(a[2]), float(a[3])
            steps = int(a[4]) if len(a) >= 5 else max(2, int(duration / 0.1))
        steps = max(1, steps)
        if duration <= 0:
            # Zero/negative duration: applies the final value directly.
            self.ctrl.set_voltage(label, v1)
            return True
        dt = duration / steps
        for k in range(1, steps + 1):
            if self._aborted():
                return False
            v = v0 + (v1 - v0) * k / steps
            self.ctrl.set_voltage(label, v)
            if not self._sleep(dt):
                return False
        return True

    def _wait_current(self, a: List[str]) -> bool:
        """Waits for a channel to satisfy ``current <op> value`` (default timeout
        30 s). Returns True if the condition is met, False on timeout or abort."""
        label, op, value = a[0], a[1], float(a[2])
        kw = _kwargs(a[3:])
        timeout = kw.get("timeout", 30.0)
        cmp = _OPS[op]
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self._aborted():
                return False
            i = self.ctrl.snapshot().channels[label].meas_current
            if cmp(i, value):
                return True
            time.sleep(0.1)
        self.ctrl.log(f"WAIT_CURRENT timeout ({label} {op} {value}).")
        return False

    def _wait_temp(self, a: List[str]) -> bool:
        """Waits for a sensor to satisfy ``temperature <op> value`` (default
        timeout 60 s). A ``NaN`` reading (sensor in fault) never satisfies the
        condition. Returns True if met, False on timeout or abort."""
        sensor, op, value = a[0], a[1], float(a[2])
        kw = _kwargs(a[3:])
        timeout = kw.get("timeout", 60.0)
        cmp = _OPS[op]
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self._aborted():
                return False
            t = self.ctrl.snapshot().temperatures.get(sensor, float("nan"))
            if t == t and cmp(t, value):  # t==t excludes NaN
                return True
            time.sleep(0.2)
        self.ctrl.log(f"WAIT_TEMP timeout ({sensor} {op} {value}).")
        return False


# ------------------------------------------------------- shutdown sequence
def build_shutdown_actions(labels: List[str], delay: float = 0.5) -> List[Action]:
    """Builds an orderly power-down sequence.

    The channels are switched off in the **reverse** order of ``labels`` (hence
    reverse of the switch-on order defined in the configuration), with a
    ``delay`` between each switch-off. Used by the *Shutdown sequence* button
    AND by the thermal safety (soft switch-off rather than an abrupt cut-off,
    to avoid damaging the board).
    """
    actions: List[Action] = []
    ln = 0
    for label in list(labels)[::-1]:
        ln += 1
        actions.append(Action(lineno=ln, cmd="OFF", args=[label], raw=f"OFF {label}"))
        if delay > 0:
            ln += 1
            actions.append(
                Action(lineno=ln, cmd="WAIT", args=[str(delay)], raw=f"WAIT {delay}")
            )
    return actions


def load_shutdown_actions(
    path, labels: List[str], valid_labels: Set[str], valid_sensors: Set[str],
    delay: float = 0.5, valid_relays: Set[str] = frozenset(),
) -> List[Action]:
    """Loads the shutdown sequence from a file if provided/existing, otherwise
    builds a default orderly switch-off."""
    from pathlib import Path

    if path:
        p = Path(path)
        if p.exists():
            return parse_sequence(p.read_text(encoding="utf-8"), valid_labels,
                                  valid_sensors, valid_relays)
    return build_shutdown_actions(labels, delay)
