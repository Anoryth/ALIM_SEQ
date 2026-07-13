"""Asservissement (servo) — mixin du :class:`Controller`.

Extrait de ``controller.py`` (décomposition de l'objet-dieu) : régulation de la
tension d'une voie jusqu'à obtenir un courant cible sur une autre. Deux stratégies —
pas fixe (:meth:`ServoMixin.servo`) et pas adaptatif sécante/Newton amorti
(:meth:`ServoMixin.servo_adaptive`). **Partage l'état** du contrôleur via ``self``
(``set_voltage``, ``_read_current_median``, ``get_setpoint``, ``_polarity``,
``_max_voltage``, ``abort_event``, ``log``) — pur déplacement de code, zéro
changement de comportement.
"""

from __future__ import annotations

import time
from typing import Callable, Optional


class ServoMixin:
    """Asservissement tension→courant. Greffé sur ``Controller``."""

    # ----------------------------------------------------- asservissement
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
        """Ajuste la tension de ``adjust_label`` jusqu'à obtenir ``target_current``
        sur ``measure_label``.

        Régulation incrémentale : à chaque pas, on lit le courant mesuré et on
        augmente/diminue la tension de ``|step|`` selon le signe de l'erreur, en
        restant dans [v_min, v_max]. Retourne True si la cible est atteinte
        (|erreur| <= tol), False sinon (timeout / borne atteinte / avortement).

        Le **sens** est déterminé automatiquement : par défaut on suppose que la
        tension et le courant varient dans le même sens (monter la tension monte
        le courant). Mettre ``invert=True`` pour un dispositif à relation inversée
        (monter la tension fait BAISSER le courant). ``step`` est une amplitude :
        son signe est ignoré (un pas négatif n'inverse PAS le sens — utiliser
        ``invert`` pour cela).
        """
        # Bornes par défaut selon la polarité de la voie réglée :
        #   polarité + : [0, +max]   |   polarité - : [-max, 0]
        pol = self._polarity(adjust_label)
        vmax_abs = self._max_voltage(adjust_label)
        if v_max is None:
            v_max = 0.0 if pol < 0 else vmax_abs
        if v_min is None:
            v_min = -vmax_abs if pol < 0 else 0.0
        step = abs(step)  # amplitude : le sens vient de l'erreur (+ invert)
        should_abort = should_abort or (lambda: self.abort_event.is_set())

        voltage = self.get_setpoint(adjust_label).set_voltage
        voltage = max(v_min, min(voltage, v_max))
        self.set_voltage(adjust_label, voltage)

        self.log(
            f"SERVO {adjust_label} -> I({measure_label})={target_current:.3f}A "
            f"(pas={step}, plage=[{v_min},{v_max}], tol={tol})"
        )

        t_start = time.monotonic()
        while True:
            if should_abort():
                self.log("SERVO avorté.")
                return False
            if time.monotonic() - t_start > timeout:
                self.log(f"SERVO timeout après {timeout:.1f}s.")
                return False

            current = self._read_current_median(measure_label)
            error = target_current - current

            if abs(error) <= tol:
                self.log(
                    f"SERVO atteint : I({measure_label})={current:.3f}A, "
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
                    f"SERVO borne atteinte (V={voltage:.3f}V) sans atteindre la "
                    f"cible (I={current:.3f}A)."
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
        """Asservissement à **pas adaptatif** (méthode de la sécante / Newton amorti).

        À chaque itération, on estime la transconductance locale ``dI/dV`` à partir
        des deux derniers points mesurés, puis on calcule le pas par
        ``ΔV = damping · erreur / pente`` — grand loin de la cible, fin tout près,
        sans gain à régler. Le pas est **plafonné à ``|step|``** (sécurité) et borné
        à ``[v_min, v_max]``.

        Replis : au 1er pas (pas encore de pente) et en **zone plate** (pente ≈ 0,
        ex. saturation), on retombe sur un pas fixe ``|step|`` dans le sens présumé
        (``invert=True`` si monter la tension fait BAISSER le courant). Dès qu'une
        pente fiable est mesurée, son signe corrige automatiquement le sens.

        Retourne True si ``|erreur| <= tol``, False sinon (timeout / borne / avortement).
        Variante à pas fixe : :meth:`servo`.
        """
        pol = self._polarity(adjust_label)
        vmax_abs = self._max_voltage(adjust_label)
        if v_max is None:
            v_max = 0.0 if pol < 0 else vmax_abs
        if v_min is None:
            v_min = -vmax_abs if pol < 0 else 0.0
        step = abs(step)
        guess = -1.0 if invert else 1.0  # sens présumé courant↑ quand tension↑
        should_abort = should_abort or (lambda: self.abort_event.is_set())

        voltage = max(v_min, min(self.get_setpoint(adjust_label).set_voltage, v_max))
        self.set_voltage(adjust_label, voltage)
        self.log(
            f"SERVO_ADAPT {adjust_label} -> I({measure_label})={target_current:.3f}A "
            f"(pas_max={step}, damping={damping}, plage=[{v_min},{v_max}], tol={tol})"
        )

        prev_v: Optional[float] = None
        prev_i: Optional[float] = None
        t_start = time.monotonic()
        while True:
            if should_abort():
                self.log("SERVO avorté.")
                return False
            if time.monotonic() - t_start > timeout:
                self.log(f"SERVO timeout après {timeout:.1f}s.")
                return False

            current = self._read_current_median(measure_label)
            error = target_current - current
            if abs(error) <= tol:
                self.log(
                    f"SERVO atteint : I({measure_label})={current:.3f}A, "
                    f"V({adjust_label})={voltage:.3f}V"
                )
                return True

            # Pente locale dI/dV estimée sur le dernier déplacement (sécante). On
            # REJETTE l'estimation si la variation de courant reste sous le plancher
            # de bruit de mesure : sinon la sécante amplifie le bruit et le pas de
            # Newton s'emballe. Plancher lié à la tolérance (échelle de résolution).
            slope = None
            noise_floor = max(0.25 * tol, 1e-4)
            if (prev_v is not None and abs(voltage - prev_v) > 1e-6
                    and abs(current - prev_i) > noise_floor):
                slope = (current - prev_i) / (voltage - prev_v)

            if slope is not None and abs(slope) > 1e-9:
                dv = damping * error / slope            # pas de Newton amorti
            else:
                dv = guess * (1.0 if error > 0 else -1.0) * step  # repli pas fixe

            dv = max(-step, min(dv, step))               # plafond de sécurité
            new_voltage = max(v_min, min(voltage + dv, v_max))
            if new_voltage == voltage:
                self.log(
                    f"SERVO borne atteinte (V={voltage:.3f}V) sans atteindre la "
                    f"cible (I={current:.3f}A)."
                )
                return False

            prev_v, prev_i = voltage, current
            voltage = new_voltage
            self.set_voltage(adjust_label, voltage)
            time.sleep(max(0.01, settle))
