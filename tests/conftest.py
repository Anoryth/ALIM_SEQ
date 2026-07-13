"""Fixtures pytest : configuration de simulation construite en code.

Indépendante de config.json (que l'utilisateur modifie) pour des tests stables.
La configuration reproduit les cas clés : voie négative, groupe série, couplage
grille->drain, capteur conditionné à une voie.
"""

from __future__ import annotations

import pytest

from alim_seq.config import AppConfig, ChannelConfig, GroupConfig, TempSensorConfig
from alim_seq.controller import Controller


def build_config(**over) -> AppConfig:
    channels = {
        "D1": ChannelConfig("D1", "PSU1", 1, 0.0, 1.0, 20.0, 1.0),
        "D2": ChannelConfig("D2", "PSU1", 2, 0.0, 1.0, 20.0, 1.0),
        "GATE": ChannelConfig("GATE", "PSU1", 4, 0.0, 0.01, 5.0, 0.01, polarity=-1.0),
        "AUX": ChannelConfig("AUX", "PSU2", 1, 5.0, 0.05, 17.0, 0.05),
        "VLOAD": ChannelConfig("VLOAD", "PSU2", 2, 6.0, 1.0, 6.0, 1.0),
    }
    groups = {
        "DRAIN": GroupConfig("DRAIN", ["D1", "D2"], "series", "equal", 40.0, 1.0),
        # Groupe dont les membres s'étalent sur DEUX alims (PSU1 + PSU2) : sert à
        # vérifier que _lock_for verrouille bien toutes les alims, sans deadlock.
        "SPAN": GroupConfig("SPAN", ["D1", "AUX"], "series", "equal", 30.0, 1.0),
    }
    temps = {
        "TS1": TempSensorConfig("TS1", "ai0", {"type": "identity"}, 60.0, 80.0,
                                requires=["VLOAD"], valid_min=-40.0, valid_max=150.0),
    }
    safety = {"poll_interval": 0.1, "temp_poll_interval": 0.05, "hard_margin_c": 15.0,
              "shutdown_delay": 0.05, "comm_fail_limit": 2,
              "shutdown_on_temp_lost": True, "shutdown_on_sensor_fault": False}
    safety.update(over.get("safety", {}))
    simulation = {
        "ambient_c": 25.0, "thermal_gain_c_per_w": 1.0, "thermal_tau_s": 1.0, "noise_c": 0.0,
        "loads": {"GATE": 1e6, "AUX": 1e6, "VLOAD": 12.0, "D1": 1000.0, "D2": 1000.0},
        "couplings": [{"gate": "GATE", "drains": ["DRAIN"], "vth": -3.0, "gm": 0.18, "imax": 1.0}],
    }
    simulation.update(over.get("simulation", {}))
    return AppConfig(simulate=True, supplies={"PSU1": {}, "PSU2": {}}, channels=channels,
                     temperatures=temps, daq={}, safety=safety, groups=groups,
                     simulation=simulation)


@pytest.fixture
def cfg() -> AppConfig:
    return build_config()


@pytest.fixture
def ctrl(cfg):
    """Contrôleur connecté, boucles ARRÊTÉES (on pilote les cycles à la main)."""
    c = Controller(cfg)
    assert c.connect() is True
    c.stop_polling()  # déterminisme : pas de threads de polling
    yield c
    c.close()
