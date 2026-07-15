"""Controller: hardware orchestration, measurement loop and safety.

The controller is the single entry point for all the business logic. It:

- builds the **instruments** (real or simulated) declared by the config, each
  exposing its **capabilities** (voltage source, V/I measurement, temperature
  measurement… — see ``alim_seq/instrument.py``); it drives them *by capability*,
  never by type;
- serializes hardware accesses with **one lock per instrument** (``_instr_locks[name]``,
  supplies as well as the temperature module). This way a VISA timeout on one
  instrument blocks neither the temperature loop nor the cut-off of the others.
  **Invariant acquisition order** (never invert it):

      instrument lock(s) (alphabetical order of the name)  ->  _state_lock

  The safety loop takes ONLY the temperature instrument's lock (never a source
  lock): a frozen source cannot delay a cut-off. For a series group, ALL the
  supplies of its members are locked, sorted by name, before any action (the
  ``_lock_for`` context manager).
- runs a **measurement loop** in the background that reads voltages, currents and
  temperatures, then evaluates safety;
- at the **critical** threshold, triggers an **orderly power-down** (soft
  switch-off of the channels, rather than an abrupt cut-off); a hard cut-off only
  happens as a last resort beyond critical + ``hard_margin_c``;
- records the measurements to a **CSV file** over time;
- exposes a thread-safe *snapshot* of the state for the GUI;
- provides the **servo control** primitive reused by the sequencer.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Deque, Dict, List, Optional, Tuple

from .config import AppConfig
from .i18n import _
from .controller_recording import RecordingMixin
from .controller_servo import ServoMixin
from .controller_simtune import SimTuneMixin
from .essai import DossierEssai, ISSUE_ARRET_UTILISATEUR, ISSUE_DECLENCHEMENT
from .instrument import Instrument, create_instrument, driver_role
from .sequencer import Action, SequenceRunner, load_shutdown_actions

# Safety levels
OK = "OK"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
NA = "NA"        # sensor "pending": not valid (required channel not yet ON)
FAULT = "FAULT"  # sensor in FAULT (out of range / disconnected) or comm loss


@dataclass
class ChannelView:
    """State of a channel (or a group) as seen by the GUI and the sequencer.

    Combines the **setpoints** (SIGNED ``set_voltage``, ``set_current``, ``output``)
    and the latest **measurements** (SIGNED ``meas_voltage``, ``meas_current``,
    CV/CC ``mode``, HMP hardware ``faults``). Voltages are signed on the software
    side: a negative rail carries a negative setpoint/measurement, only the
    magnitude is programmed on the supply (see :meth:`Controller.set_voltage`)."""
    label: str
    set_voltage: float = 0.0
    set_current: float = 0.1
    output: bool = False
    meas_voltage: float = 0.0
    meas_current: float = 0.0
    mode: str = ""  # "CV", "CC" or "" (channel OFF / unknown)
    faults: tuple = ()  # HMP hardware faults: 'OVP', 'FUSE', 'OTP'


@dataclass
class Snapshot:
    """Consistent, thread-safe snapshot of the whole state, produced by
    :meth:`Controller.snapshot`. The GUI reads it at its display rate without ever
    touching the hardware: channels, temperatures and per-sensor status, global
    safety state, connection/communication, hardware fault and the two loops'
    actual rates."""
    channels: Dict[str, ChannelView]
    temperatures: Dict[str, float]
    temp_status: Dict[str, str]
    safety_status: str
    safety_message: str
    tripped: bool
    connected: bool = True
    comm_lost: bool = False
    hw_fault: str = ""  # HMP hardware fault (OVP/fuse/overtemperature), empty if none
    meas_period: float = 0.0
    temp_period: float = 0.0
    relays: Dict[str, bool] = field(default_factory=dict)  # relay outputs (label->state)
    # Channels whose source instrument could not be read on the last cycle (frozen
    # link): their displayed V/I are STALE -> the GUI greys them out ("⏱ frozen").
    stale_labels: set = field(default_factory=set)
    timestamp: float = field(default_factory=time.monotonic)


class Controller(RecordingMixin, ServoMixin, SimTuneMixin):
    """Central orchestrator: hardware, measurement/safety loops, sequencer.

    The cohesive periphery is carried by mixins (pure code move, same ``self``
    state): :class:`~alim_seq.controller_recording.RecordingMixin` (CSV recording /
    test folder), :class:`~alim_seq.controller_servo.ServoMixin` (servo control) and
    :class:`~alim_seq.controller_simtune.SimTuneMixin` (simulated couplings + live
    tuning). The safety core (loops, locks, lifecycle, shutdowns, escalation) stays
    here, cohesive and auditable.

    Built from an :class:`~alim_seq.config.AppConfig`. Typical lifecycle:
    ``Controller(cfg)`` → :meth:`connect` (starts the loops) → control via
    :meth:`set_voltage` / :meth:`set_output` / :meth:`servo` or a sequence
    (:meth:`start_user_sequence`) → :meth:`snapshot` for display →
    :meth:`close`. Every hardware access is serialized by the locks described in the
    module docstring; no method assumes it runs in the GUI thread."""

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        # One hardware lock PER supply + one for the NI module (see the module
        # docstring for the invariant acquisition order).
        # Internal name of the temperature instrument (NI module / mock), guaranteed
        # distinct from the supply names: used as the lock key and for routing.
        self._daq_name = self._pick_daq_name()
        # One hardware lock PER instrument (sources + temperature). See the module
        # docstring for the invariant acquisition order (alphabetical by name). The
        # names come from the unified ``instruments`` section (+ the temperature
        # instrument, synthesized if the config declares none).
        self._instr_locks: Dict[str, threading.RLock] = {
            name: threading.RLock()
            for name in set(cfg.instruments) | {self._daq_name}
        }
        self._state_lock = threading.Lock()
        self._logs: Deque[str] = deque(maxlen=1000)
        self._log_lock = threading.Lock()
        # Log subscribers (the test folder attaches to it for the duration of a
        # test). Called from log() outside the log lock, exceptions swallowed.
        self._log_listeners: List[Callable[[str], None]] = []
        self._log_listeners_lock = threading.Lock()

        # Current setpoints (what was requested), indexed by label.
        self._set: Dict[str, ChannelView] = {
            label: ChannelView(
                label=label,
                set_voltage=ch.default_voltage,
                set_current=ch.default_current,
            )
            for label, ch in cfg.channels.items()
        }

        # Last known measurements (updated by the measurement loop).
        self._temperatures: Dict[str, float] = {n: float("nan") for n in cfg.temperatures}
        self._temp_voltages: Dict[str, float] = {n: float("nan") for n in cfg.temperatures}
        self._temp_status: Dict[str, str] = {n: OK for n in cfg.temperatures}
        self._safety_status = OK
        self._safety_message = ""
        self._tripped = False
        self._hard_cut_done = False

        # Connection / communication state.
        self._connected = False
        self._connect_error = ""
        self._comm_lost = False
        self._psu_fail = 0
        self._daq_fail = 0

        # HMP hardware faults (OVP / fuse / overtemperature) read from the register.
        self._hw_fault_msg = ""
        self._hw_fault_seen: set = set()

        # Actual measured rate (effective period between two cycles, in s).
        self._meas_period = 0.0
        self._temp_period = 0.0
        # Consecutive V/I measurement cycles where the instrument could not be
        # locked (frozen link?) — used to log the anomaly without blocking the loop.
        self._meas_skip: Dict[str, int] = {}
        # Last successfully read relay states (relay_states is non-blocking: if a
        # lock is busy, the last known value is reused rather than nothing).
        self._relay_states_cache: Dict[str, bool] = {}

        self._build_instruments()
        # Temperature monitoring: disabled if no sensor is defined
        # ('temperatures': {}). The NI module is then NOT used.
        self._temp_enabled = bool(self.cfg.temperatures)

        # Two loops: temperatures (safety, fast) and V/I measurements (slow).
        self._temp_thread: Optional[threading.Thread] = None
        self._meas_thread: Optional[threading.Thread] = None
        self._stop_poll = threading.Event()
        # Abort flag used by the sequencer (safety / stop).
        self.abort_event = threading.Event()

        # Automatic reconnection (opt-in): a watchdog tries to reopen the link after
        # a communication loss, with exponential back-off.
        # _reconnect_lock serializes reconnect(): the watchdog AND the GUI's
        # "Reconnect" button can request it at the same instant — without this
        # lock, two instrument rebuilds would interleave.
        self._reconnect_lock = threading.Lock()
        self._auto_reconnect = bool(cfg.safety.get("auto_reconnect", False))
        self._reconnect_max_delay = float(cfg.safety.get("reconnect_max_delay", 30.0))
        self._wd_thread: Optional[threading.Thread] = None
        self._wd_stop = threading.Event()

        # Sequencer (runs sequence files and the power-down).
        self.runner = SequenceRunner(self)
        # The controller intercepts the end of a sequence to mark the test outcome,
        # then relays it to the GUI via ``on_seq_finish`` (which the GUI wires up).
        self.runner.on_finish = self._runner_finished
        self.on_seq_finish: Optional[Callable[[bool, str], None]] = None
        self._shutdown_inflight = threading.Event()  # avoids a double trigger
        # Path of the shutdown sequence file (None = automatic orderly power-off).
        self._shutdown_path: Optional[str] = cfg.safety.get("shutdown_sequence")

        # CSV recording.
        self._csv_file = None
        self._csv_writer = None
        self._csv_path: Optional[Path] = None
        self._csv_t0: float = 0.0
        self._rec_lock = threading.Lock()
        # Current test folder (None outside a recording, or a "raw CSV" recording
        # to an explicit path with no folder).
        self._essai: Optional[DossierEssai] = None

        # Application log (file) — disabled until enable_file_logging is called
        # (so the tests do not create a file).
        self._file_logger: Optional[logging.Logger] = None

    # ------------------------------------------------------------------ build
    def _pick_daq_name(self) -> str:
        """Name of the temperature instrument: the first declared instrument that is
        neither a source nor an actuator (relay), otherwise a distinct synthetic name
        (the controller always has a temperature instrument, even without a sensor)."""
        for name, e in self.cfg.instruments.items():
            if driver_role(str((e or {}).get("driver", "HMP4040"))) not in ("source", "actuator"):
                return name
        name = "TEMP"
        while name in self.cfg.instruments:
            name += "_"
        return name

    def _build_instruments(self) -> None:
        """Builds all the instruments from the unified ``instruments`` section, and
        the label→(instrument, channel) routing. Each entry is classified **by
        capability** via its ``driver`` (voltage source vs temperature) and built by
        the **unified registry** ``create_instrument``.

        ``self._instruments`` maps name→instrument, ``self._source_names`` lists the
        sources, and ``self._daq`` points to the *MesureTemperature* instrument. In
        simulation, applies the ``simulation.loads`` resistive loads to each channel."""
        self._routing: Dict[str, Tuple[str, int]] = {
            label: (ch.supply, ch.channel) for label, ch in self.cfg.channels.items()
        }

        # Simulated loads per channel (ohms), from simulation.loads (label -> ohms).
        # Converted to {supply_name: {channel: ohms}} for each mock.
        loads_cfg = self.cfg.simulation.get("loads", {}) if self.cfg.simulate else {}
        per_supply_loads: Dict[str, Dict[int, float]] = {}
        for label, ohms in loads_cfg.items():
            if label in self._routing:
                sname, ch = self._routing[label]
                per_supply_loads.setdefault(sname, {})[ch] = float(ohms)

        # Relay output routing: label -> (instrument, safe state).
        relay_map = self.cfg.relay_map
        outs_by_instr: Dict[str, List[str]] = {}
        for lbl, meta in relay_map.items():
            outs_by_instr.setdefault(meta["instrument"], []).append(lbl)

        instruments: Dict[str, Instrument] = {}
        self._source_names: List[str] = []
        self._relay_names: List[str] = []
        self._relay_routing: Dict[str, Tuple[str, bool]] = {}
        for name, entry in self.cfg.instruments.items():
            driver = str((entry or {}).get("driver", "HMP4040"))
            role = driver_role(driver)
            if role == "source":
                instruments[name] = create_instrument(
                    driver, simulate=self.cfg.simulate, name=name,
                    resource=(entry or {}).get("resource", ""),
                    loads=per_supply_loads.get(name),
                    visa_backend=self.cfg.visa_backend,
                    use_cc_status=self.cfg.cc_status,
                    query_delay_s=self.cfg.visa_query_delay,
                    log=self.log,
                )
                self._source_names.append(name)
            elif role == "actuator":
                instruments[name] = create_instrument(
                    driver, simulate=self.cfg.simulate, name=name,
                    outputs=outs_by_instr.get(name, []),
                )
                self._relay_names.append(name)
                for lbl in outs_by_instr.get(name, []):
                    self._relay_routing[lbl] = (name, bool(relay_map[lbl].get("safe_state", False)))
            else:  # MesureTemperature capability (single instrument, see validation)
                instruments[name] = self._make_daq_instrument(name, entry or {})
        # Safety net: if no temperature instrument is declared, synthesize one (the
        # controller always has one, even without a configured sensor).
        if self._daq_name not in instruments:
            instruments[self._daq_name] = self._make_daq_instrument(self._daq_name, {})
        self._instruments = instruments
        self._daq = instruments[self._daq_name]

    def _make_daq_instrument(self, name: str, entry: Dict[str, object]) -> Instrument:
        """Temperature instrument: ``MockDAQ`` (thermal model driven by the
        dissipated power) in simulation, real NI module otherwise — via
        ``create_instrument``. Sensors come from ``temperatures``; ``entry`` carries
        the driver parameters (e.g. ``device`` on real hardware)."""
        if self.cfg.simulate:
            sim = self.cfg.simulation
            return create_instrument(
                "NI-DAQ", simulate=True, name=name,
                sensors=self.cfg.temperatures,
                power_provider=self._total_output_power,
                ambient_c=sim.get("ambient_c", 25.0),
                thermal_gain_c_per_w=sim.get("thermal_gain_c_per_w", 6.0),
                thermal_tau_s=sim.get("thermal_tau_s", 8.0),
                noise_c=sim.get("noise_c", 0.15),
            )
        return create_instrument(
            "NI-DAQ", simulate=False, name=name,
            sensors=self.cfg.temperatures,
            device=str(entry.get("device", self.cfg.daq.get("device", "Dev1"))),
        )

    def _sources(self):
        """Iterates ``(name, instrument)`` of the voltage sources, in name order."""
        for name in self._source_names:
            yield name, self._instruments[name]

    def _route(self, label: str) -> Tuple[Instrument, int]:
        """Instrument (source) and physical channel of a logical channel."""
        name, ch = self._routing[label]
        return self._instruments[name], ch

    def _total_output_power(self) -> float:
        """Total delivered power (used by the simulated thermal model).

        Deliberately WITHOUT a lock: ``output_power`` only reads an in-memory mock
        state (no VISA I/O) and this function is called by MockDAQ's power provider
        *under* the temperature instrument's lock. Taking a source lock here would
        invert the invariant order and could deadlock.
        """
        total = 0.0
        for _name, psu in self._sources():
            if hasattr(psu, "output_power"):
                for ch in range(1, psu.n_channels + 1):
                    total += psu.output_power(ch)  # type: ignore[attr-defined]
        return total

    # --------------------------------------------------------- hardware locks
    def _supply_names_for(self, label: str) -> List[str]:
        """Supplies concerned by a label (channel or group), sorted by name
        (deterministic acquisition order -> no deadlock)."""
        if label in self.cfg.groups:
            names = {self._routing[m][0] for m in self.cfg.groups[label].members
                     if m in self._routing}
        elif label in self._routing:
            names = {self._routing[label][0]}
        else:
            names = set()
        return sorted(names)

    @contextmanager
    def _lock_for(self, label: str):
        """Locks all the supplies of a label (channel/group), in sorted order."""
        acquired = []
        try:
            for name in self._supply_names_for(label):
                lk = self._instr_locks[name]
                lk.acquire()
                acquired.append(lk)
            yield
        finally:
            for lk in reversed(acquired):
                lk.release()

    @contextmanager
    def _all_instr_locked(self):
        """Locks ALL the instruments (order sorted by name). Reserved for global
        operations run with polling STOPPED (connect/reconnect/close): deadlock-free
        by the ordering, and without contention since no loop runs at those times."""
        acquired = []
        try:
            for name in sorted(self._instr_locks):
                lk = self._instr_locks[name]
                lk.acquire()
                acquired.append(lk)
            yield
        finally:
            for lk in reversed(acquired):
                lk.release()

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> bool:
        """Attempts the connection. Does NOT raise: returns True/False and fills in
        ``connect_error`` so the GUI stays alive on failure."""
        errors = []
        # Connection: polling stopped (or not yet started) -> all locks can be taken
        # (sorted order + daq), deadlock-free.
        with self._all_instr_locked():
            try:
                for _name, psu in self._sources():
                    psu.connect()
            except Exception as exc:
                errors.append(_("Power supplies: {}").format(exc))
            if self._temp_enabled:
                try:
                    self._daq.connect()
                except Exception as exc:
                    errors.append(_("NI acquisition: {}").format(exc))
            if not errors:
                # Default setpoints (magnitude accounting for polarity), OFF.
                try:
                    for label, view in self._set.items():
                        pol = self.cfg.channels[label].polarity
                        inst, ch = self._route(label)
                        inst.set_voltage(ch, pol * view.set_voltage)
                        inst.set_current(ch, view.set_current)
                        inst.set_output(ch, False)
                except Exception as exc:
                    errors.append(_("Channel initialization: {}").format(exc))

        if errors:
            self._connected = False
            self._connect_error = "\n".join(errors)
            self.log(_("Connection failed:") + "\n  " + "\n  ".join(errors))
            return False

        self._install_sim_couplings()
        self._connected = True
        self._connect_error = ""
        self._comm_lost = False
        self._psu_fail = 0
        self._daq_fail = 0
        self.log(_("Hardware connected ({}).").format(
            _("SIMULATION") if self.cfg.simulate else _("REAL")))
        self.start_polling()
        self._start_watchdog()
        return True

    def _start_watchdog(self) -> None:
        if not self._auto_reconnect or (self._wd_thread and self._wd_thread.is_alive()):
            return
        self._wd_stop.clear()
        self._wd_thread = threading.Thread(target=self._watchdog_loop, name="watchdog",
                                           daemon=True)
        self._wd_thread.start()

    def _watchdog_loop(self) -> None:
        """Reconnection watchdog: tries to reopen the link after a communication
        loss, with exponential back-off (outside a running sequence)."""
        delay = 2.0
        while not self._wd_stop.wait(1.0):
            if self._comm_lost and not self.runner.is_running:
                self.log(_("Auto-reconnect in {:.0f} s…").format(delay))
                if self._wd_stop.wait(delay):
                    break
                if self._comm_lost and self.reconnect():
                    delay = 2.0
                else:
                    delay = min(delay * 2.0, self._reconnect_max_delay)

    def reconnect(self) -> bool:
        """Closes and reopens fresh hardware sessions (after a fault/disconnection).

        Serialized by ``_reconnect_lock``: the watchdog and the GUI's "Reconnect"
        button can call it at the same time — the second request is refused (False)
        rather than interleaving two instrument rebuilds."""
        if not self._reconnect_lock.acquire(blocking=False):
            self.log(_("Reconnection already in progress — request ignored."))
            return False
        try:
            self.log(_("Attempting to reconnect…"))
            self.stop_polling()
            with self._all_instr_locked():
                for name in list(self._source_names) + [self._daq_name]:
                    try:
                        self._instruments[name].close()
                    except Exception:
                        pass
            # Fresh VISA/NI sessions (same names -> the locks stay valid).
            self._build_instruments()
            return self.connect()
        finally:
            self._reconnect_lock.release()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def connect_error(self) -> str:
        return self._connect_error

    @property
    def comm_lost(self) -> bool:
        return self._comm_lost

    # Simulation: gate->drain couplings + live tuning -> SimTuneMixin
    # (alim_seq/controller_simtune.py).

    def close(self) -> None:
        """Clean application shutdown: stops the watchdog, interrupts any sequence
        (even a safety power-down), stops the loops and the recording, cuts off all
        channels and closes the hardware sessions. Best-effort: every step is
        protected so the shutdown runs to completion."""
        self._wd_stop.set()
        if self._wd_thread:
            self._wd_thread.join(timeout=2.0)
        self.runner.force_stop()   # app shutdown: interrupts everything, even a power-down
        self.stop_polling()
        self.stop_recording()
        with self._all_instr_locked():
            for _name, psu in self._sources():
                try:
                    psu.all_outputs_off()
                except Exception:
                    pass
            for name in list(self._source_names) + [self._daq_name]:
                try:
                    self._instruments[name].close()
                except Exception:
                    pass
        self._connected = False
        self.log(_("Hardware disconnected."))

    # ----------------------------------------------------------------- logs
    def enable_file_logging(self, path: Optional[str] = None,
                            max_bytes: int = 2_000_000, backups: int = 3) -> Path:
        """Enables writing the application log to a file (rotation).

        Call once at startup (main.py). No effect if already active.
        Returns the log file's path.
        """
        from logging.handlers import RotatingFileHandler

        if self._file_logger is not None:
            return Path(self._file_logger.handlers[0].baseFilename)  # already active

        if path is None:
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            path = logs_dir / "alim_seq.log"
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger(f"alim_seq.{id(self)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups,
                                      encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        self._file_logger = logger
        self.log(_("Application log: {}").format(path))
        return Path(path)

    def add_log_listener(self, cb: Callable[[str], None]) -> None:
        """Subscribes ``cb`` to the log: it receives each formatted line. Used by
        the test folder to write ``journal.log``."""
        with self._log_listeners_lock:
            if cb not in self._log_listeners:
                self._log_listeners.append(cb)

    def remove_log_listener(self, cb: Callable[[str], None]) -> None:
        with self._log_listeners_lock:
            if cb in self._log_listeners:
                self._log_listeners.remove(cb)

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        with self._log_lock:
            self._logs.append(line)
        if self._file_logger is not None:
            try:
                self._file_logger.info(message)
            except Exception:
                pass
        # Subscribers notified outside the lock (a slow/failing subscriber does not
        # block the log; its exceptions are swallowed).
        with self._log_listeners_lock:
            listeners = list(self._log_listeners)
        for cb in listeners:
            try:
                cb(line)
            except Exception:
                pass

    def drain_logs(self) -> list[str]:
        with self._log_lock:
            out = list(self._logs)
            self._logs.clear()
        return out

    # ---------------------------------------------------------- channel commands
    def _clamp(self, label: str, voltage=None, current=None):
        ch = self.cfg.channels[label]
        if voltage is not None:
            voltage = float(voltage)
            # SIGNED voltage: [0, max] for + polarity, [-max, 0] for - polarity.
            if ch.polarity >= 0:
                voltage = max(0.0, min(voltage, ch.max_voltage))
            else:
                voltage = max(-ch.max_voltage, min(voltage, 0.0))
        if current is not None:
            current = max(0.0, min(float(current), ch.max_current))
        return voltage, current

    def set_voltage(self, label: str, voltage: float) -> None:
        """Sets the SIGNED voltage of a channel (or splits it over a series group).

        The value is bounded by the clamp (``[0,max]`` or ``[-max,0]`` depending on
        the polarity); only the **magnitude** is programmed on the supply (the HMP
        only outputs positive), the sign staying handled on the software side. Takes
        the lock of the concerned supply/supplies."""
        if label in self.cfg.groups:
            return self._set_group_voltage(label, voltage)
        voltage, _ = self._clamp(label, voltage=voltage)
        # The MAGNITUDE is programmed on the supply (positive), the sign is kept on
        # the software side.
        magnitude = self.cfg.channels[label].polarity * voltage
        with self._lock_for(label):
            inst, ch = self._route(label)
            inst.set_voltage(ch, magnitude)
        with self._state_lock:
            self._set[label].set_voltage = voltage

    def set_current(self, label: str, current: float) -> None:
        """Sets a channel's current limit (bounded to ``[0, max]``).

        For a series group, applies the SAME limit to each member, bounded by the
        group's limit (a series stack cools less well: its limit can be lower than
        that of the individual channels)."""
        if label in self.cfg.groups:
            # Series channels: same current limit on each member, bounded by the
            # GROUP's limit (GroupConfig.max_current) which can be lower than that
            # of the members (series stack cools less well).
            g = self.cfg.groups[label]
            current = max(0.0, min(float(current), self._group_max_current(g)))
            for m in g.members:
                self.set_current(m, current)
            return
        _, current = self._clamp(label, current=current)
        with self._lock_for(label):
            inst, ch = self._route(label)
            inst.set_current(ch, current)
        with self._state_lock:
            self._set[label].set_current = current

    def set_output(self, label: str, on: bool) -> None:
        """Switches a channel (or a series group) on/off.

        A group switches on in the order of its members and off in reverse order.
        Any switch-on is REFUSED while safety is armed (``tripped``): it must be
        rearmed first."""
        if label in self.cfg.groups:
            # Switch-on in the order of the members, switch-off in reverse order.
            members = self.cfg.groups[label].members
            for m in (members if on else list(reversed(members))):
                self.set_output(m, on)
            self.log(_("Series group {} {}").format(label, 'ON' if on else 'OFF'))
            return
        if on and self._tripped:
            self.log(_("Refused: safety active (tripped). Rearm before switching on."))
            return
        with self._lock_for(label):
            # Re-check UNDER the lock (as in set_relay): a trip occurring between the
            # test above and the acquisition must not let a switch-ON through — the
            # channel powers the board directly, so this guard matters even more here.
            if on and self._tripped:
                self.log(_("Refused: safety active (tripped). Rearm before switching on."))
                return
            inst, ch = self._route(label)
            inst.set_output(ch, bool(on))
        with self._state_lock:
            self._set[label].output = bool(on)
        self.log(_("Channel {} {}").format(label, 'ON' if on else 'OFF'))

    def get_setpoint(self, label: str) -> ChannelView:
        """Current setpoints (voltage/current/state) of a channel or a group, without
        touching the hardware. For the full measured state, prefer :meth:`snapshot`."""
        if label in self.cfg.groups:
            return self._group_view(label)
        with self._state_lock:
            v = self._set[label]
            return ChannelView(v.label, v.set_voltage, v.set_current, v.output)

    # ----------------------------------------------------------- relays (actuators)
    def set_relay(self, label: str, on: bool) -> None:
        """Closes (``on=True``) or opens a relay output, under its instrument's lock.
        Any **closing** (ON) is refused while safety is armed (``tripped``), as for
        switching a channel on: a relay can re-power the board. Driving to the safe
        state (:meth:`_drive_relays_safe`) bypasses this guard since it is part of
        the power-down."""
        if label not in self._relay_routing:
            raise KeyError(_("Unknown relay output: {!r}").format(label))
        if on and self._tripped:
            self.log(_("Refused: safety active (tripped). Rearm before closing a relay."))
            return
        name, _safe = self._relay_routing[label]
        with self._instr_locks[name]:
            # Re-check UNDER the lock: a trip occurring between the test above and
            # the acquisition must not let a closing through.
            if on and self._tripped:
                self.log(_("Refused: safety active (tripped). Rearm before closing a relay."))
                return
            self._instruments[name].set_state(label, bool(on))
        self.log(_("Relay {} {}").format(
            label, _("ON (closed)") if on else _("OFF (open)")))

    def relay_state(self, label: str) -> Optional[bool]:
        """Current state of a relay output (``None`` if unknown)."""
        if label not in self._relay_routing:
            raise KeyError(_("Unknown relay output: {!r}").format(label))
        name, _safe = self._relay_routing[label]
        with self._instr_locks[name]:
            return self._instruments[name].get_state(label)

    def relay_states(self) -> Dict[str, bool]:
        """State of all relay outputs (``{label: bool}``), for the GUI.

        Non-blocking: an instrument whose lock is busy is served the **last
        successful reading** (cache) rather than omitted — the GUI never displays a
        ghost OFF for a relay that is actually closed."""
        out: Dict[str, bool] = dict(self._relay_states_cache)
        for name in self._relay_names:
            lk = self._instr_locks.get(name)
            got = lk.acquire(blocking=False) if lk else False
            if not got:
                continue   # lock busy: keep the last known value
            try:
                out.update(self._instruments[name].states())
            except Exception:
                pass
            finally:
                lk.release()
        self._relay_states_cache = dict(out)
        return out

    def _drive_relays_safe(self) -> None:
        """Sets each relay output to its configured **safe state** (default
        OFF/open). Used by the orderly power-down and the emergency stop: opening a
        relay isolates the board. Lock taken NON-blocking (safety must never be
        delayed by a frozen instrument); best-effort."""
        for name in sorted(self._relay_names):
            lk = self._instr_locks.get(name)
            got = lk.acquire(blocking=False) if lk else False
            try:
                inst = self._instruments[name]
                for lbl, (iname, safe) in self._relay_routing.items():
                    if iname == name:
                        inst.set_state(lbl, safe)
            except Exception as exc:
                self.log(_("Relay {} safe-state error: {}").format(name, exc))
            finally:
                if got:
                    lk.release()

    # ----------------------------------------------- groups (series channels)
    def _group_max_voltage(self, g) -> float:
        if g.max_voltage > 0:
            return g.max_voltage
        return sum(self.cfg.channels[m].max_voltage for m in g.members)

    def _group_max_current(self, g) -> float:
        """Group current limit: explicit ``max_current`` (> 0) otherwise the
        smallest of the members' ``max_current`` (series -> same current everywhere)."""
        if g.max_current > 0:
            return g.max_current
        return min(self.cfg.channels[m].max_current for m in g.members)

    def _split_voltage(self, g, total: float) -> List[float]:
        """Splits the total voltage between the members (per-channel caps honored)."""
        members = g.members
        maxes = [self.cfg.channels[m].max_voltage for m in members]
        total = max(0.0, min(total, sum(maxes)))
        alloc = [0.0] * len(members)
        if g.split == "fill":
            # Fills each channel up to its max, in order.
            remaining = total
            for i, mx in enumerate(maxes):
                alloc[i] = min(mx, remaining)
                remaining -= alloc[i]
            return alloc
        # "equal": balanced split with overflow (water-filling).
        remaining = total
        active = list(range(len(members)))
        while remaining > 1e-9 and active:
            share = remaining / len(active)
            progressed = False
            for i in list(active):
                give = min(share, maxes[i] - alloc[i])
                alloc[i] += give
                remaining -= give
                if give > 1e-9:
                    progressed = True
                if alloc[i] >= maxes[i] - 1e-9:
                    active.remove(i)
            if not progressed:
                break
        return alloc

    def _set_group_voltage(self, label: str, total: float) -> None:
        g = self.cfg.groups[label]
        total = max(0.0, min(float(total), self._group_max_voltage(g)))
        alloc = self._split_voltage(g, total)
        for m, av in zip(g.members, alloc):
            self.set_voltage(m, av)  # physical channel: clamp + setpoint tracking

    def _group_view(self, label: str) -> ChannelView:
        """Aggregated view of a series group, derived from the state of the member
        channels."""
        g = self.cfg.groups[label]
        with self._state_lock:
            views = [self._set[m] for m in g.members]
            set_v = sum(v.set_voltage for v in views)
            set_i = min(v.set_current for v in views)
            output = all(v.output for v in views)
            meas_v = sum(v.meas_voltage for v in views)
            currents = [v.meas_current for v in views]
            modes = [v.mode for v in views]
        meas_i = sum(currents) / len(currents) if currents else 0.0
        # The group is in CC if at least one member channel is.
        if not output:
            mode = ""
        elif "CC" in modes:
            mode = "CC"
        else:
            mode = "CV"
        return ChannelView(label, set_v, set_i, output, meas_v, meas_i, mode)

    def _read_current(self, label: str) -> float:
        """Measured current of a channel/group (self-locking: takes the PSU
        lock(s) of the label)."""
        with self._lock_for(label):
            if label in self.cfg.groups:
                members = self.cfg.groups[label].members
                vals = []
                for m in members:
                    inst, ch = self._route(m)
                    vals.append(inst.measure_current(ch))
                return sum(vals) / len(vals) if vals else 0.0
            inst, ch = self._route(label)
            return inst.measure_current(ch)

    def _read_current_median(self, label: str, n: int = 3) -> float:
        """Median of ``n`` current readings spaced ~10 ms apart. Measurement noise
        on a SINGLE reading makes the servo oscillate around the target; the median
        dampens it without introducing a noticeable delay."""
        if n <= 1:
            return self._read_current(label)
        vals = [self._read_current(label)]
        for _i in range(n - 1):
            time.sleep(0.01)
            vals.append(self._read_current(label))
        vals.sort()
        return vals[len(vals) // 2]

    def _max_voltage(self, label: str) -> float:
        if label in self.cfg.groups:
            return self._group_max_voltage(self.cfg.groups[label])
        return self.cfg.channels[label].max_voltage

    def _polarity(self, label: str) -> float:
        if label in self.cfg.groups:
            first = self.cfg.groups[label].members[0]
            return self.cfg.channels[first].polarity
        return self.cfg.channels[label].polarity

    def voltage_bounds(self, label: str) -> Tuple[float, float]:
        """SIGNED voltage bounds of a channel/group for the GUI: ``[0, +max]`` for
        positive polarity, ``[-max, 0]`` for negative. The controller's clamp stays
        authoritative; these bounds are only an input aid."""
        mx = self._max_voltage(label)
        return (0.0, mx) if self._polarity(label) >= 0 else (-mx, 0.0)

    def current_bounds(self, label: str) -> Tuple[float, float]:
        """Current-limit bounds of a channel/group for the GUI: ``[0, max]``
        (group: the group's ``max_current`` otherwise the smallest of the members)."""
        if label in self.cfg.groups:
            return 0.0, self._group_max_current(self.cfg.groups[label])
        return 0.0, self.cfg.channels[label].max_current

    def eval_expression(self, expr: str) -> float:
        """Evaluates a setpoint expression (e.g. ``(VD/2)+VG1``) against the current
        state. A bare channel name evaluates to its voltage setpoint."""
        from .expressions import evaluate

        snap = self.snapshot()

        def resolver(kind: str, label: str) -> float:
            if label not in snap.channels:
                raise KeyError(_("unknown channel in expression: {!r}").format(label))
            cv = snap.channels[label]
            if kind == "V":
                return cv.set_voltage
            if kind == "Vmeas":
                return cv.meas_voltage
            if kind == "Iset":
                return cv.set_current
            if kind == "Imeas":
                return cv.meas_current
            raise ValueError(_("unknown quantity: {}").format(kind))

        return evaluate(expr, resolver)

    # ------------------------------------------------- sequence (orchestration)
    @property
    def is_sequence_running(self) -> bool:
        return self.runner.is_running

    def start_user_sequence(self, actions: List[Action], text: str = "") -> None:
        """Starts a user sequence (refused if safety is armed).

        ``text`` is the exact sequence text: if provided and a recording is in
        progress, it is archived in ``sequence.seq``."""
        if not self._connected or self._comm_lost:
            self.log(_("Refused: hardware not connected. Check the link before "
                       "starting a sequence."))
            return
        if self._tripped:
            self.log(_("Refused: safety active. Rearm before starting a sequence."))
            return
        if text and self._essai is not None:
            self._essai.write_sequence(text)
        self.runner.start(actions)

    def stop_sequence(self) -> None:
        """Interrupts the running user sequence (without cutting off the channels).
        No effect — and logged — during a safety power-down."""
        if self._essai is not None:
            self._essai.set_issue(ISSUE_ARRET_UTILISATEUR)
        if not self.runner.stop():
            self.log(_("Stop refused: safety power-down in progress."))

    def set_shutdown_sequence(self, path: Optional[str], log: bool = True) -> None:
        """Sets the shutdown sequence file (None/"" = automatic orderly channel
        power-off). Used by the *Shutdown sequence* button AND by the safety
        power-down."""
        self._shutdown_path = path or None
        if not log:
            return
        if self._shutdown_path:
            self.log(_("Shutdown sequence: {}").format(self._shutdown_path))
        else:
            self.log(_("Shutdown sequence: automatic orderly power-off."))

    @property
    def shutdown_path(self) -> Optional[str]:
        return self._shutdown_path

    @property
    def is_shutting_down(self) -> bool:
        """True while a power-down (orderly or safety) is in progress."""
        return self._shutdown_inflight.is_set()

    def start_shutdown_sequence(self, reason: Optional[str] = None, trip: bool = False) -> None:
        """Triggers the **orderly power-down** (soft switch-off of the channels).

        Used by the *Shutdown sequence* button (``trip=False``) and by the thermal
        safety (``trip=True``: the lock is armed to prevent any switch-back-on, but
        the switch-off is clean rather than abrupt).
        """
        if self._shutdown_inflight.is_set():
            return
        self._shutdown_inflight.set()
        if trip:
            with self._state_lock:
                self._tripped = True
                self._safety_status = CRITICAL
                self._safety_message = reason or _("Safety power-down")
            self.log(_("!!! {} — orderly power-down in progress.").format(reason))
            self._mark_safety_issue("trip", reason or _("Safety power-down"))
        else:
            self.log(_("Shutdown sequence triggered."))
        threading.Thread(target=self._shutdown_worker, daemon=True).start()

    def _shutdown_worker(self) -> None:
        """Runs the orderly power-down. NEVER leaves the board powered: any failure
        (stuck user sequence, ``runner.start`` raising, power-down timeout,
        unexpected exception) falls back to a hard cut-off via :meth:`emergency_stop`
        (idempotent, best-effort)."""
        try:
            # 1) Takes over any running user sequence (force_stop: OUR sequence is
            #    about to launch instead, the intent is unconditional).
            self.runner.force_stop()
            wait_s = float(self.cfg.safety.get("shutdown_takeover_wait_s", 3.0))
            deadline = time.monotonic() + max(0.0, wait_s)
            while self.runner.is_running and time.monotonic() < deadline:
                time.sleep(0.05)
            if self.runner.is_running:
                # The sequence refuses to exit (thread stuck in a timed-out VISA
                # query?): the orderly power-down cannot be launched (runner.start
                # would raise) -> immediate hard cut-off.
                self.log(_("User sequence stuck: switching to hard cut-off."))
                self.emergency_stop(
                    _("Orderly power-down impossible (sequence stuck) — hard cut-off"))
                return

            # 2) Loads the shutdown actions (falls back to auto power-off if invalid).
            try:
                actions = load_shutdown_actions(
                    self._shutdown_path,
                    labels=list(self.cfg.channels),
                    valid_labels=set(self.cfg.all_labels),
                    valid_sensors=set(self.cfg.temperatures),
                    delay=float(self.cfg.safety.get("shutdown_delay", 0.5)),
                    valid_relays=set(self.cfg.relay_labels),
                )
            except Exception as exc:
                from .sequencer import build_shutdown_actions
                self.log(_("Invalid shutdown sequence ({}) — automatic power-off.").format(exc))
                actions = build_shutdown_actions(
                    list(self.cfg.channels), float(self.cfg.safety.get("shutdown_delay", 0.5))
                )

            # 3) Runs with a time guard: beyond the budget, hard cut-off.
            from .sequencer import estimate_duration
            budget = float(self.cfg.safety.get(
                "shutdown_timeout", estimate_duration(actions) + 30.0))
            self.runner.start(actions, safety_mode=True)  # runs even with the lock armed
            deadline = time.monotonic() + max(1.0, budget)
            while self.runner.is_running:
                if time.monotonic() > deadline:
                    self.log(_("Power-down too long (> {:.0f}s) — hard cut-off.").format(budget))
                    self.emergency_stop(
                        _("Orderly power-down timed out — hard cut-off"))
                    break
                time.sleep(0.05)
        except Exception as exc:
            # Last resort: whatever happens, we try to cut off the channels.
            self.log(_("Orderly power-down failed: {}").format(exc))
            try:
                self.emergency_stop(
                    _("Orderly power-down impossible ({}) — hard cut-off").format(exc))
            except Exception:
                pass
        finally:
            # Whatever the outcome, the relays end up in the safe state (the sources
            # are cut off at this point -> we isolate).
            self._drive_relays_safe()
            self._shutdown_inflight.clear()

    # ------------------------------------------------------------- safety
    def _mark_safety_issue(self, kind: str, message: str) -> None:
        """Records a safety event and the "trip" outcome in the current test folder
        (no effect outside a recording)."""
        essai = self._essai
        if essai is None:
            return
        essai.set_issue(ISSUE_DECLENCHEMENT, cause=message)
        essai.add_safety_event(kind, message)

    def emergency_stop(self, reason: Optional[str] = None) -> None:
        """IMMEDIATELY cuts off all channels and arms the safety lock.

        Abrupt cut-off reserved for the operator emergency stop and the last-resort
        hard cut-off. For a soft stop, see :meth:`start_shutdown_sequence`.
        """
        if reason is None:
            reason = _("Emergency stop")
        self.abort_event.set()
        self.runner.force_stop()   # interrupts even a running safety power-down
        # Cut off supply by supply, lock taken NON-blocking: a dead supply (frozen
        # VISA, lock held by a stuck read) must NOT delay the cut-off of the others.
        # Safety comes first: the switch-off is attempted even without the lock.
        for name in sorted(self._source_names):
            lk = self._instr_locks.get(name)
            got = lk.acquire(blocking=False) if lk else False
            try:
                self._instruments[name].all_outputs_off()
            except Exception as exc:
                self.log(_("Cut-off {} error: {}").format(name, exc))
            finally:
                if got:
                    lk.release()
        with self._state_lock:
            for v in self._set.values():
                v.output = False
            self._tripped = True
            self._hard_cut_done = True
            self._safety_status = CRITICAL
            self._safety_message = reason
        # Relays set to the safe state (isolation) AFTER arming the trip: a
        # concurrent closing arriving in the meantime is thus either refused
        # (tripped), or overridden here — never a relay left closed during a trip.
        self._drive_relays_safe()
        self.log(_("!!! {} — all channels cut off.").format(reason))
        self._mark_safety_issue("coupure_dure", reason)

    def reset_safety(self) -> None:
        """Rearms after a trip (only use once the fault has been cleared)."""
        with self._state_lock:
            self._tripped = False
            self._hard_cut_done = False
            self._comm_lost = False
            self._psu_fail = 0
            self._daq_fail = 0
            self._hw_fault_msg = ""
            self._hw_fault_seen = set()
            self._safety_status = OK
            self._safety_message = ""
        self.abort_event.clear()
        self.log(_("Safety rearmed."))

    @property
    def tripped(self) -> bool:
        return self._tripped

    # CSV recording / test folder: see RecordingMixin
    # (alim_seq/controller_recording.py).

    # --------------------------------------- measurement / safety loops
    def start_polling(self) -> None:
        """Starts the two background threads: temperature (safety, fast) and V/I
        measurements (display, slower). The temperature loop is only launched if
        sensors are configured. Idempotent (does not relaunch a live thread)."""
        self._stop_poll.clear()
        if self._temp_enabled and not (self._temp_thread and self._temp_thread.is_alive()):
            self._temp_thread = threading.Thread(target=self._temp_loop, name="temp", daemon=True)
            self._temp_thread.start()
        if not (self._meas_thread and self._meas_thread.is_alive()):
            self._meas_thread = threading.Thread(target=self._meas_loop, name="meas", daemon=True)
            self._meas_thread.start()

    def stop_polling(self) -> None:
        """Stops the two background loops and waits for the threads to end (bounded
        join)."""
        self._stop_poll.set()
        for t in (self._temp_thread, self._meas_thread):
            # ``ident`` is None until the thread has started: only JOIN threads that
            # actually launched (a failed ``start()`` would otherwise leave a
            # not-started object -> join() would raise "before it is started").
            if t is not None and t.ident is not None:
                t.join(timeout=2.0)

    # --- TEMPERATURE loop (safety, fast rate) --------------------------------
    def _temp_loop(self) -> None:
        """Thermal safety loop (``temp`` thread). Reads temperatures at
        ``temp_poll_interval`` (fast), measures the actual rate, and on a repeated
        error triggers the measurement-loss handling. Independent from the supplies:
        a frozen VISA cannot slow it down."""
        interval = float(self.cfg.safety.get(
            "temp_poll_interval", self.cfg.safety.get("poll_interval", 0.5)))
        last = None
        while not self._stop_poll.is_set():
            t0 = time.monotonic()
            if last is not None:
                self._temp_period = t0 - last
            last = t0
            try:
                self._temp_cycle()
                self._daq_fail = 0
            except Exception as exc:
                self._daq_fail += 1
                self.log(_("Temperature read error: {}").format(exc))
                self._handle_temp_failure()
            self._stop_poll.wait(max(0.0, interval - (time.monotonic() - t0)))

    def _temp_cycle(self) -> None:
        """One safety cycle: reads temperatures, classifies each sensor, computes
        the global status, then applies the safety escalation — (1) HARD cut-off if
        a sensor exceeds critical + ``hard_margin_c``, (2) ORDERLY power-down at the
        critical threshold, (3) power-down on a faulty sensor if configured."""
        # Thermal loop: depends ONLY on the temperature instrument. No source lock
        # held here -> a frozen VISA on a supply cannot delay safety.
        with self._instr_locks[self._daq_name]:
            temps = self._daq.read_temperatures()
            volts = self._daq.read_voltages()  # raw NI voltages (safety net)
        ready = {n: self._sensor_ready(s) for n, s in self.cfg.temperatures.items()}
        per_sensor = {
            n: self._classify_sensor(n, temps.get(n, float("nan")), ready[n])
            for n in self.cfg.temperatures
        }
        status, message, crit_sensor, fault_sensor = self._overall_temp_status(temps, per_sensor)

        with self._state_lock:
            self._temperatures = temps
            self._temp_voltages = volts
            self._temp_status = per_sensor
            if not self._tripped and not self._comm_lost:
                self._safety_status = status
                self._safety_message = message

        # 1) Last-resort HARD cut-off (NA/FAULT sensors excluded).
        hard_margin = float(self.cfg.safety.get("hard_margin_c", 15.0))
        for name, t in temps.items():
            if per_sensor[name] in (NA, FAULT):
                continue
            if t == t and t >= self.cfg.temperatures[name].critical + hard_margin:
                if not self._hard_cut_done:
                    self.emergency_stop(
                        _("Hard cut-off: {} = {:.1f}°C "
                          "(> critical + {:.0f}°C)").format(name, t, hard_margin)
                    )
                return

        # 2) Critical threshold -> ORDERLY (soft) power-down.
        if status == CRITICAL and not self._tripped:
            if self.cfg.safety.get("auto_shutdown_on_critical", True):
                self.start_shutdown_sequence(
                    reason=_("Critical temperature {} = {:.1f}°C").format(
                        crit_sensor, temps[crit_sensor]),
                    trip=True,
                )
            return

        # 3) Sensor in FAULT -> power-down only if configured.
        if fault_sensor and not self._tripped \
                and self.cfg.safety.get("shutdown_on_sensor_fault", False):
            self.start_shutdown_sequence(
                reason=_("Sensor fault: {}").format(fault_sensor), trip=True)

    def _handle_temp_failure(self) -> None:
        """After ``comm_fail_limit`` consecutive temperature read errors, declares
        the measurement lost. Since the supplies probably still respond, the
        power-down can be SOFT (if channels are ON and ``shutdown_on_temp_lost``)."""
        limit = int(self.cfg.safety.get("comm_fail_limit", 3))
        if self._daq_fail < limit or self._comm_lost:
            return
        any_on = any(self._set[l].output for l in self.cfg.channels)
        msg = _("Temperature measurement lost (NI module)")
        # The supplies probably still communicate -> a SOFT power-down is possible.
        gentle = any_on and self.cfg.safety.get("shutdown_on_temp_lost", True)
        self._declare_comm_lost(msg, gentle=gentle, shutdown=any_on)

    # --- V/I MEASUREMENT loop (display / logs, slower rate) -----------------
    def _meas_loop(self) -> None:
        """V/I measurement loop (``meas`` thread). Reads voltages/currents/mode at
        ``poll_interval`` (slower, SCPI latency), feeds the display and the CSV, and
        on a repeated error triggers the supply communication-loss handling."""
        interval = float(self.cfg.safety.get("poll_interval", 0.5))
        last = None
        while not self._stop_poll.is_set():
            t0 = time.monotonic()
            if last is not None:
                self._meas_period = t0 - last
            last = t0
            try:
                self._meas_cycle()
                self._psu_fail = 0
            except Exception as exc:
                self._psu_fail += 1
                self.log(_("Power-supply measurement error: {}").format(exc))
                self._handle_psu_failure()
            self._stop_poll.wait(max(0.0, interval - (time.monotonic() - t0)))

    def _meas_cycle(self) -> None:
        """One measurement cycle: reads V/I/mode/faults of each channel (supply by
        supply, each under its own lock, acquired **with a timeout** — a supply
        whose lock is unavailable is skipped this cycle, never blocking), updates
        the state, reports HMP hardware faults and writes a CSV row if a recording
        is in progress."""
        with self._state_lock:
            sp = {l: (self._set[l].set_voltage, self._set[l].set_current,
                      self._set[l].output, self._set[l].mode)
                  for l in self.cfg.channels}
        meas: Dict[str, Tuple[float, float]] = {}
        modes: Dict[str, str] = {}
        faults: Dict[str, tuple] = {}
        # Measured supply by supply, each under ITS OWN lock. Acquired WITH A
        # TIMEOUT: a lock held by a hung VISA call (dead socket, inoperative
        # timeout) would otherwise silently block the WHOLE loop — no exception,
        # hence no comm-loss detection. An unavailable supply is SKIPPED this cycle
        # (last values kept) and logged after several failed cycles.
        by_supply: Dict[str, List[str]] = {}
        for label in self.cfg.channels:
            name = self._routing[label][0]
            by_supply.setdefault(name, []).append(label)
        skipped: List[str] = []
        for name in sorted(by_supply):
            lk = self._instr_locks[name]
            if not lk.acquire(timeout=1.0):
                skipped.extend(by_supply[name])
                n = self._meas_skip.get(name, 0) + 1
                self._meas_skip[name] = n
                if n == 5:
                    self.log(_("!!! Measurements {}: instrument unavailable for {} "
                               "cycles (VISA link frozen?) — values frozen.").format(name, n))
                continue
            try:
                inst = self._instruments[name]
                for label in by_supply[name]:
                    ch = self._routing[label][1]
                    v = self.cfg.channels[label].polarity * inst.measure_voltage(ch)
                    i = inst.measure_current(ch)
                    st = inst.measure_status(ch)  # 1 query: mode + faults
                    meas[label] = (v, i)
                    modes[label] = st.get("mode") or self._infer_mode(sp[label], v, i)
                    faults[label] = tuple(st.get("faults") or ())
            finally:
                lk.release()
            if self._meas_skip.get(name, 0) >= 5:
                self.log(_("Measurements {}: instrument available again.").format(name))
            self._meas_skip[name] = 0
        with self._state_lock:
            for label, (v, i) in meas.items():
                self._set[label].meas_voltage = v
                self._set[label].meas_current = i
                self._set[label].mode = modes[label]
                self._set[label].faults = faults[label]
            # Skipped channels: filled in with the LAST known values so the CSV and
            # the faults stay continuous (no false 0 V / 0 A).
            for label in skipped:
                meas[label] = (self._set[label].meas_voltage,
                               self._set[label].meas_current)
                faults[label] = self._set[label].faults
            temps = dict(self._temperatures)
            volts = dict(self._temp_voltages)
            status = self._safety_status
        self._handle_hw_faults(faults)
        self._record_row(meas, temps, volts, status)

    def _handle_hw_faults(self, faults: Dict[str, tuple]) -> None:
        """Reports the HMP hardware faults (OVP/fuse/overtemperature).

        Logs each new fault, updates the banner, and triggers an orderly power-down
        if ``safety.shutdown_on_hw_fault`` is true.
        """
        active = {label: f for label, f in faults.items() if f}
        labels = ["{} [{}]".format(label, "/".join(f)) for label, f in active.items()]
        with self._state_lock:
            self._hw_fault_msg = _("Supply fault: ") + ", ".join(labels) if labels else ""
        # Logs the new (channel, fault) pairs.
        current = {(label, code) for label, fs in active.items() for code in fs}
        for label, code in current - self._hw_fault_seen:
            self.log(_("!!! Hardware fault {} on channel {}").format(code, label))
        self._hw_fault_seen = current
        if active and not self._tripped \
                and self.cfg.safety.get("shutdown_on_hw_fault", False):
            self.start_shutdown_sequence(
                reason=_("Supply hardware fault: ") + ", ".join(labels), trip=True)

    def _handle_psu_failure(self) -> None:
        """After ``comm_fail_limit`` consecutive supply measurement errors, declares
        the communication lost. Since the supply is unreachable, a clean ramp is
        impossible → emergency cut-off (best effort)."""
        limit = int(self.cfg.safety.get("comm_fail_limit", 3))
        if self._psu_fail < limit or self._comm_lost:
            return
        # Unreachable supply: a clean ramp is not possible -> emergency cut-off
        # (best effort, it may fail but we try).
        self._declare_comm_lost(
            _("Communication lost with a power supply"), gentle=False, shutdown=True)

    def _declare_comm_lost(self, msg: str, gentle: bool, shutdown: bool) -> None:
        """Switches to the communication-loss state (``FAULT``) and, if
        ``shutdown``, powers down: softly (``gentle=True``, the supplies still
        respond) or via a hard cut-off (``gentle=False``, unreachable supply —
        best effort)."""
        with self._state_lock:
            self._comm_lost = True
            self._safety_status = FAULT
            self._safety_message = msg
        self.log(f"!!! {msg}")
        self._mark_safety_issue("perte_comm", msg)
        if not shutdown:
            return
        if gentle:
            self.start_shutdown_sequence(reason=msg, trip=True)
        else:
            self.emergency_stop(msg)

    @staticmethod
    def _infer_mode(sp: Tuple[float, float, bool, str], v: float, i: float) -> str:
        """Infers CV/CC from the setpoints and the measurements (signed V).

        Since the HMP4040 does not expose a CC/CV state in SCPI, the mode is
        deduced from two signals: current close to the limit, and/or measured
        voltage noticeably below the setpoint. A **hysteresis** (distinct 'strong'
        thresholds to enter and exit CC) prevents the display from flickering at
        the switch point.
        """
        vset, iset, out, prev = sp
        if not out:
            return ""
        vmag = abs(vset)
        vdrop = vmag - abs(v)
        cc_strong = (iset > 0 and i >= iset * 0.99) or \
                    (vmag > 0.05 and vdrop > max(0.07 * vmag, 0.05))
        cv_strong = (iset <= 0 or i <= iset * 0.90) and \
                    (vmag <= 0.05 or vdrop < max(0.03 * vmag, 0.02))
        if prev == "CC":
            return "CV" if cv_strong else "CC"
        if prev == "CV":
            return "CC" if cc_strong else "CV"
        return "CC" if cc_strong else "CV"

    def _classify_sensor(self, name: str, temp: float, ready: bool) -> str:
        """Classifies a sensor: ``NA`` (required channel not yet ON), ``FAULT``
        (NaN, out of the plausibility band, or bridge reference voltage out of
        tolerance), otherwise a thermal level ``OK``/``WARNING``/``CRITICAL``. A
        ``NA`` or ``FAULT`` sensor is excluded from the safety calculation (never a
        falsely plausible value)."""
        if not ready:
            return NA
        s = self.cfg.temperatures[name]
        if temp != temp:  # NaN
            return FAULT
        if (s.valid_min is not None and temp < s.valid_min) or \
           (s.valid_max is not None and temp > s.valid_max):
            return FAULT
        # Optional check of the bridge's reference voltage: if the channel
        # supplying it strays too far from the expected v_ref, the measurement is
        # not trustworthy.
        if s.ref_channel:
            vref = s.expected_vref
            if vref:
                meas = abs(self._measured_voltage(s.ref_channel))
                if meas == meas and abs(meas - vref) > s.ref_tol * abs(vref):
                    return FAULT
        return self._sensor_level(name, temp)

    def _measured_voltage(self, label: str) -> float:
        """MEASURED (signed) voltage of a channel or a group (sum of the members)."""
        with self._state_lock:
            if label in self.cfg.groups:
                return sum(self._set[m].meas_voltage for m in self.cfg.groups[label].members)
            v = self._set.get(label)
            return v.meas_voltage if v else float("nan")

    def _sensor_level(self, name: str, temp: float) -> str:
        s = self.cfg.temperatures[name]
        if temp >= s.critical:
            return CRITICAL
        if temp >= s.warning:
            return WARNING
        return OK

    def _channel_is_on(self, label: str) -> bool:
        if label in self.cfg.groups:
            return all(self._set[m].output for m in self.cfg.groups[label].members)
        v = self._set.get(label)
        return bool(v and v.output)

    def _sensor_ready(self, sensor) -> bool:
        """The sensor is valid if all its 'requires' channels are ON."""
        return all(self._channel_is_on(req) for req in sensor.requires)

    def _overall_temp_status(self, temps, per_sensor):
        """Returns (status, message, critical_sensor, faulty_sensor).
        Increasing severity rank: OK < WARNING < FAULT < CRITICAL."""
        order = {OK: 0, WARNING: 1, FAULT: 2, CRITICAL: 3}
        worst, message = OK, ""
        crit_sensor = fault_sensor = None
        for name, lvl in per_sensor.items():
            if lvl == NA:
                continue
            if lvl == FAULT and fault_sensor is None:
                fault_sensor = name
            if lvl == CRITICAL and crit_sensor is None:
                crit_sensor = name
            if order.get(lvl, 0) > order.get(worst, 0):
                worst = lvl
                if lvl == FAULT:
                    message = _("{}: sensor fault").format(name)
                elif lvl == CRITICAL:
                    message = _("{} = {:.1f}°C >= critical").format(name, temps[name])
                elif lvl == WARNING:
                    message = _("{} = {:.1f}°C >= warning").format(name, temps[name])
        return worst, message, crit_sensor, fault_sensor

    # ------------------------------------------------------------- snapshot
    def snapshot(self) -> Snapshot:
        """Returns a consistent :class:`Snapshot` of the whole state (channels,
        groups, temperatures, safety, connection). Thread-safe and without hardware
        I/O: it is the single read point for the GUI and for ``eval_expression``."""
        with self._state_lock:
            channels = {
                label: ChannelView(
                    v.label, v.set_voltage, v.set_current, v.output,
                    v.meas_voltage, v.meas_current, v.mode, v.faults,
                )
                for label, v in self._set.items()
            }
        # Aggregated views of series groups (outside the lock: _group_view retakes it).
        for gname in self.cfg.groups:
            channels[gname] = self._group_view(gname)
        # Relay states (outside _state_lock: takes the relay instrument locks).
        relays = self.relay_states() if self._relay_names else {}
        # Channels whose source instrument was skipped on the last measurement
        # cycle (frozen VISA link): their V/I are stale.
        stale = {label for label in self.cfg.channels
                 if self._meas_skip.get(self._routing[label][0], 0) > 0}
        with self._state_lock:
            return Snapshot(
                channels=channels,
                temperatures=dict(self._temperatures),
                temp_status=dict(self._temp_status),
                safety_status=self._safety_status,
                safety_message=self._safety_message,
                tripped=self._tripped,
                connected=self._connected,
                comm_lost=self._comm_lost,
                hw_fault=self._hw_fault_msg,
                meas_period=self._meas_period,
                temp_period=self._temp_period,
                relays=relays,
                stale_labels=stale,
            )

    # Servo control (servo / servo_adaptive): see ServoMixin
    # (alim_seq/controller_servo.py).
