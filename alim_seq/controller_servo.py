"""Servo control — :class:`Controller` mixin.

Extracted from ``controller.py`` (god-object decomposition): regulates a channel's
voltage until a target current is reached on another. Two strategies — fixed step
(:meth:`ServoMixin.servo`) and damped secant/Newton adaptive step
(:meth:`ServoMixin.servo_adaptive`). **Shares the controller's state** via ``self``
(``set_voltage``, ``_read_current_median``, ``get_setpoint``, ``_polarity``,
``_max_voltage``, ``abort_event``, ``log``) — pure code move, zero behavior change.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from .i18n import _


class ServoMixin:
    """Voltage→current servo control. Grafted onto ``Controller``."""

    # ----------------------------------------------------- servo control
    def servo(
        self,
        adjust_label: str,
        measure_label: str,
        target_current: float,
        step: float = 0.02,
        v_min: Optional[float] = None,
        v_max: Optional[float] = None,
        tol: float = 0.01,
        timeout: float = 30.0,
        settle: float = 0.3,
        invert: bool = False,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Adjusts ``adjust_label``'s voltage until ``target_current`` is reached
        on ``measure_label``.

        Incremental regulation: at each step, the measured current is read and the
        voltage is increased/decreased by ``|step|`` according to the error's sign,
        staying within [v_min, v_max]. Returns True if the target is reached
        (|error| <= tol), False otherwise (timeout / bound reached / abort).

        The **direction** is determined automatically: by default the voltage and
        the current are assumed to vary in the same direction (raising the voltage
        raises the current). Set ``invert=True`` for a device with an inverted
        relation (raising the voltage LOWERS the current). ``step`` is a magnitude:
        its sign is ignored (a negative step does NOT invert the direction — use
        ``invert`` for that).
        """
        # Default bounds according to the adjusted channel's polarity:
        #   + polarity: [0, +max]   |   - polarity: [-max, 0]
        pol = self._polarity(adjust_label)
        vmax_abs = self._max_voltage(adjust_label)
        if v_max is None:
            v_max = 0.0 if pol < 0 else vmax_abs
        if v_min is None:
            v_min = -vmax_abs if pol < 0 else 0.0
        step = abs(step)  # magnitude: the direction comes from the error (+ invert)
        should_abort = should_abort or (lambda: self.abort_event.is_set())

        voltage = self.get_setpoint(adjust_label).set_voltage
        voltage = max(v_min, min(voltage, v_max))
        self.set_voltage(adjust_label, voltage)

        self.log(
            f"SERVO {adjust_label} -> I({measure_label})={target_current:.3f}A "
            f"(step={step}, range=[{v_min},{v_max}], tol={tol})"
        )

        t_start = time.monotonic()
        while True:
            if should_abort():
                self.log(_("SERVO aborted."))
                return False
            if time.monotonic() - t_start > timeout:
                self.log(_("SERVO timeout after {:.1f}s.").format(timeout))
                return False

            current = self._read_current_median(measure_label)
            error = target_current - current

            if abs(error) <= tol:
                self.log(
                    f"SERVO reached: I({measure_label})={current:.3f}A, "
                    f"V({adjust_label})={voltage:.3f}V"
                )
                return True

            direction = 1.0 if error > 0 else -1.0
            if invert:
                direction = -direction
            new_voltage = max(v_min, min(voltage + direction * step, v_max))
            if new_voltage == voltage and (
                (direction > 0 and voltage >= v_max) or (direction < 0 and voltage <= v_min)
            ):
                self.log(
                    f"SERVO bound reached (V={voltage:.3f}V) without reaching "
                    f"the target (I={current:.3f}A)."
                )
                return False
            voltage = new_voltage
            self.set_voltage(adjust_label, voltage)
            time.sleep(max(0.01, settle))

    def servo_adaptive(
        self,
        adjust_label: str,
        measure_label: str,
        target_current: float,
        step: float = 0.5,
        v_min: Optional[float] = None,
        v_max: Optional[float] = None,
        tol: float = 0.01,
        timeout: float = 30.0,
        settle: float = 0.3,
        invert: bool = False,
        damping: float = 0.7,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """**Adaptive-step** servo control (damped secant / Newton method).

        At each iteration, the local transconductance ``dI/dV`` is estimated from
        the last two measured points, then the step is computed as ``ΔV = damping ·
        error / slope`` — large far from the target, fine near it, with no gain to
        tune. The step is **capped at ``|step|``** (safety) and bounded to
        ``[v_min, v_max]``.

        Fallbacks: on the 1st step (no slope yet) and in a **flat zone** (slope ≈ 0,
        e.g. saturation), it falls back to a fixed step ``|step|`` in the presumed
        direction (``invert=True`` if raising the voltage LOWERS the current). As
        soon as a reliable slope is measured, its sign automatically corrects the
        direction.

        Returns True if ``|error| <= tol``, False otherwise (timeout / bound /
        abort). Fixed-step variant: :meth:`servo`.
        """
        pol = self._polarity(adjust_label)
        vmax_abs = self._max_voltage(adjust_label)
        if v_max is None:
            v_max = 0.0 if pol < 0 else vmax_abs
        if v_min is None:
            v_min = -vmax_abs if pol < 0 else 0.0
        step = abs(step)
        guess = -1.0 if invert else 1.0  # presumed direction current↑ when voltage↑
        should_abort = should_abort or (lambda: self.abort_event.is_set())

        voltage = max(v_min, min(self.get_setpoint(adjust_label).set_voltage, v_max))
        self.set_voltage(adjust_label, voltage)
        self.log(
            f"SERVO_ADAPT {adjust_label} -> I({measure_label})={target_current:.3f}A "
            f"(max_step={step}, damping={damping}, range=[{v_min},{v_max}], tol={tol})"
        )

        prev_v: Optional[float] = None
        prev_i: Optional[float] = None
        t_start = time.monotonic()
        while True:
            if should_abort():
                self.log(_("SERVO aborted."))
                return False
            if time.monotonic() - t_start > timeout:
                self.log(_("SERVO timeout after {:.1f}s.").format(timeout))
                return False

            current = self._read_current_median(measure_label)
            error = target_current - current
            if abs(error) <= tol:
                self.log(
                    f"SERVO reached: I({measure_label})={current:.3f}A, "
                    f"V({adjust_label})={voltage:.3f}V"
                )
                return True

            # Local slope dI/dV estimated on the last move (secant). The estimate
            # is REJECTED if the current variation stays below the measurement
            # noise floor: otherwise the secant amplifies the noise and the Newton
            # step runs away. Floor tied to the tolerance (resolution scale).
            slope = None
            noise_floor = max(0.25 * tol, 1e-4)
            if (prev_v is not None and abs(voltage - prev_v) > 1e-6
                    and abs(current - prev_i) > noise_floor):
                slope = (current - prev_i) / (voltage - prev_v)

            if slope is not None and abs(slope) > 1e-9:
                dv = damping * error / slope            # damped Newton step
            else:
                dv = guess * (1.0 if error > 0 else -1.0) * step  # fixed-step fallback

            dv = max(-step, min(dv, step))               # safety cap
            new_voltage = max(v_min, min(voltage + dv, v_max))
            if new_voltage == voltage:
                self.log(
                    f"SERVO bound reached (V={voltage:.3f}V) without reaching "
                    f"the target (I={current:.3f}A)."
                )
                return False

            prev_v, prev_i = voltage, current
            voltage = new_voltage
            self.set_voltage(adjust_label, voltage)
            time.sleep(max(0.01, settle))
