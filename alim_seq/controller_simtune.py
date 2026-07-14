"""Live tuning of the simulated bench — :class:`Controller` mixin.

Extracted from ``controller.py`` (god-object decomposition): installs the simulated
gate→drain couplings and live-tunes the loads, the thermal model and the couplings
(GUI's Simulation tab). No effect in real mode. **Shares the controller's state**
via ``self`` (``cfg``, ``_route``/``_routing``, ``_instruments``, ``_instr_locks``,
``_daq``/``_daq_name``, ``_source_names``, ``_set``, ``log``) — pure code move, zero
behavior change.

``_install_sim_couplings`` is still called by the core's ``connect``/``reconnect``.
"""

from __future__ import annotations

from typing import Dict, List

from .i18n import _


class SimTuneMixin:
    """Simulated couplings + live tuning of the simulation. Grafted onto ``Controller``."""

    def _install_sim_couplings(self) -> None:
        """Installs the simplified gate->drain model on the simulated supplies.

        For each coupling: the drain current Id = gm*(Vgate - vth), bounded to
        [0, imax], is imposed on the 'drain' channels (current sink); the gate is
        made high-impedance (current ~0). No effect in real mode.
        """
        if not self.cfg.simulate:
            return
        for c in self.cfg.simulation.get("couplings", []):
            gate = c["gate"]
            vth = float(c.get("vth", 2.0))
            gm = float(c.get("gm", 0.005))
            imax = float(c.get("imax", 0.02))
            drains: List[str] = []
            for d in c.get("drains", []):
                if d in self.cfg.groups:
                    drains.extend(self.cfg.groups[d].members)
                else:
                    drains.append(d)

            def make_drain_source(gate_label: str, gm=gm, vth=vth, imax=imax):
                def src() -> float:
                    gv = self._set.get(gate_label)
                    if gv is None or not gv.output:
                        return 0.0
                    return max(0.0, min(gm * (gv.set_voltage - vth), imax))
                return src

            source = make_drain_source(gate)
            for d in drains:
                try:
                    psu, ch = self._route(d)
                except KeyError:
                    self.log(_("Sim coupling: unknown drain channel {!r}, ignored.").format(d))
                    continue
                if hasattr(psu, "set_current_source"):
                    psu.set_current_source(ch, source)
            try:
                gpsu, gch = self._route(gate)
                if hasattr(gpsu, "set_current_source"):
                    gpsu.set_current_source(gch, lambda: 0.0)  # high-impedance gate
            except KeyError:
                self.log(_("Sim coupling: unknown gate {!r}.").format(gate))
            self.log(
                _("Sim coupling installed: {} -> {} (Id=gm*(Vg-{}), gm={}, imax={})").format(
                    gate, drains, vth, gm, imax)
            )

    # ----------------------------------------- live tuning of the simulation
    # Thermal model defaults (mirrors _make_daq_instrument).
    _SIM_THERMAL_DEFAULTS = {
        "ambient_c": 25.0, "thermal_gain_c_per_w": 6.0,
        "thermal_tau_s": 8.0, "noise_c": 0.15,
    }

    def sim_params(self) -> Dict[str, object]:
        """Current simulation parameters (loads, thermal model, couplings),
        completed with their default values. Intended for the simulation
        configuration GUI. Meaningless in real mode."""
        sim = self.cfg.simulation
        loads = {}
        for label in self.cfg.channels:
            inst, ch = self._route(label)
            loads[label] = float(getattr(inst, "loads", {}).get(ch, 10.0)) \
                if hasattr(inst, "loads") else 0.0
        thermal = {k: float(sim.get(k, d)) for k, d in self._SIM_THERMAL_DEFAULTS.items()}
        return {"loads": loads, "thermal": thermal,
                "couplings": [dict(c) for c in sim.get("couplings", [])]}

    def sim_set_load(self, label: str, ohms: float) -> None:
        """Live-changes a channel's simulated resistive load (Ω). No effect outside
        simulation. Also updates ``cfg.simulation`` (kept across a reconnect / a
        config save)."""
        if not self.cfg.simulate or label not in self.cfg.channels:
            return
        ohms = max(0.0, float(ohms))
        name, ch = self._routing[label]
        with self._instr_locks[name]:
            inst = self._instruments[name]
            if hasattr(inst, "set_load"):
                inst.set_load(ch, ohms)
        self.cfg.simulation.setdefault("loads", {})[label] = ohms

    def sim_set_thermal(self, **params) -> None:
        """Live-changes the simulated thermal model (``ambient_c``,
        ``thermal_gain_c_per_w``, ``thermal_tau_s``, ``noise_c``). No effect outside
        simulation."""
        if not self.cfg.simulate:
            return
        with self._instr_locks[self._daq_name]:
            daq = self._daq
            for key, val in params.items():
                if key not in self._SIM_THERMAL_DEFAULTS or val is None:
                    continue
                val = float(val)
                self.cfg.simulation[key] = val
                if key == "ambient_c" and hasattr(daq, "ambient"):
                    daq.ambient = val
                elif key == "thermal_gain_c_per_w" and hasattr(daq, "gain"):
                    daq.gain = val
                elif key == "thermal_tau_s" and hasattr(daq, "tau"):
                    daq.tau = max(val, 0.1)
                elif key == "noise_c" and hasattr(daq, "noise"):
                    daq.noise = val

    def sim_set_couplings(self, couplings: List[dict]) -> None:
        """Live-replaces the simulated gate→drain couplings and reinstalls them."""
        if not self.cfg.simulate:
            return
        self.cfg.simulation["couplings"] = [dict(c) for c in couplings]
        # First removes the existing driven current sources (otherwise a
        # removed/changed coupling would leave its source in place), then reinstalls.
        for name in self._source_names:
            inst = self._instruments[name]
            srcs = getattr(inst, "_current_source", None)
            if srcs is None:
                continue
            with self._instr_locks[name]:
                for ch in list(srcs.keys()):
                    inst.set_current_source(ch, None)
        self._install_sim_couplings()
