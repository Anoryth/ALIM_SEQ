"""Réglage à chaud du banc simulé — mixin du :class:`Controller`.

Extrait de ``controller.py`` (décomposition de l'objet-dieu) : installation des
couplages grille→drain simulés et réglage en direct des charges, du modèle thermique
et des couplages (onglet Simulation de l'IHM). Sans effet en mode réel. **Partage
l'état** du contrôleur via ``self`` (``cfg``, ``_route``/``_routing``,
``_instruments``, ``_instr_locks``, ``_daq``/``_daq_name``, ``_source_names``,
``_set``, ``log``) — pur déplacement de code, zéro changement de comportement.

``_install_sim_couplings`` reste appelé par ``connect``/``reconnect`` du cœur.
"""

from __future__ import annotations

from typing import Dict, List


class SimTuneMixin:
    """Couplages simulés + réglage à chaud de la simulation. Greffé sur ``Controller``."""

    def _install_sim_couplings(self) -> None:
        """Installe le modèle simplifié grille->drain sur les alims simulées.

        Pour chaque couplage : le courant de drain Id = gm*(Vgrille - vth), borné
        à [0, imax], est imposé aux voies 'drains' (puits de courant) ; la grille
        est rendue haute impédance (courant ~0). Aucun effet en mode réel.
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
                    self.log(f"Couplage simu : voie drain inconnue {d!r}, ignorée.")
                    continue
                if hasattr(psu, "set_current_source"):
                    psu.set_current_source(ch, source)
            try:
                gpsu, gch = self._route(gate)
                if hasattr(gpsu, "set_current_source"):
                    gpsu.set_current_source(gch, lambda: 0.0)  # grille haute impédance
            except KeyError:
                self.log(f"Couplage simu : grille inconnue {gate!r}.")
            self.log(
                f"Couplage simu installé : {gate} -> {drains} "
                f"(Id=gm*(Vg-{vth}), gm={gm}, imax={imax})"
            )

    # ----------------------------------------- réglage à chaud de la simulation
    # Défauts du modèle thermique (miroir de _make_daq_instrument).
    _SIM_THERMAL_DEFAULTS = {
        "ambient_c": 25.0, "thermal_gain_c_per_w": 6.0,
        "thermal_tau_s": 8.0, "noise_c": 0.15,
    }

    def sim_params(self) -> Dict[str, object]:
        """Paramètres de simulation courants (charges, modèle thermique, couplages),
        complétés par leurs valeurs par défaut. Destiné à l'IHM de configuration de
        la simulation. Vide de sens en mode réel."""
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
        """Change à chaud la charge résistive simulée d'une voie (Ω). Sans effet hors
        simulation. Met aussi à jour ``cfg.simulation`` (conservé au travers d'un
        reconnect / d'un enregistrement de config)."""
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
        """Change à chaud le modèle thermique simulé (``ambient_c``,
        ``thermal_gain_c_per_w``, ``thermal_tau_s``, ``noise_c``). Sans effet hors
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
        """Remplace à chaud les couplages grille→drain simulés et les réinstalle."""
        if not self.cfg.simulate:
            return
        self.cfg.simulation["couplings"] = [dict(c) for c in couplings]
        # On retire d'abord les sources de courant pilotées existantes (sinon un
        # couplage supprimé/modifié laisserait sa source en place), puis on réinstalle.
        for name in self._source_names:
            inst = self._instruments[name]
            srcs = getattr(inst, "_current_source", None)
            if srcs is None:
                continue
            with self._instr_locks[name]:
                for ch in list(srcs.keys()):
                    inst.set_current_source(ch, None)
        self._install_sim_couplings()
