"""Réglage à chaud de la simulation : charges, thermique, couplages."""

from alim_seq.controller import Controller


def test_sim_params_reports_loads_and_thermal(cfg):
    c = Controller(cfg)
    c.connect()
    p = c.sim_params()
    assert set(p["loads"]) == set(cfg.channels)
    assert set(p["thermal"]) == {"ambient_c", "thermal_gain_c_per_w",
                                 "thermal_tau_s", "noise_c"}
    assert p["thermal"]["ambient_c"] == 25.0        # valeur de la fixture
    assert p["couplings"]                           # la fixture déclare 1 couplage
    c.close()


def test_sim_set_load_changes_measured_current(cfg):
    c = Controller(cfg)
    c.connect()
    # VLOAD est une charge résistive simple (D1/D2 sont pilotés par le couplage).
    c.set_voltage("VLOAD", 3.0)
    c.set_current("VLOAD", 1.0)
    c.set_output("VLOAD", True)
    c.sim_set_load("VLOAD", 10.0)
    c._meas_cycle()
    i10 = c.snapshot().channels["VLOAD"].meas_current
    c.sim_set_load("VLOAD", 5.0)     # charge deux fois plus faible -> courant doublé
    c._meas_cycle()
    i5 = c.snapshot().channels["VLOAD"].meas_current
    assert i5 > 1.5 * i10
    assert cfg.simulation["loads"]["VLOAD"] == 5.0   # mémorisé (survit à un reconnect)
    c.close()


def test_sim_set_thermal_updates_model(cfg):
    c = Controller(cfg)
    c.connect()
    c.sim_set_thermal(ambient_c=40.0, thermal_gain_c_per_w=2.0,
                      thermal_tau_s=0.0, noise_c=0.0)
    assert cfg.simulation["ambient_c"] == 40.0
    daq = c._daq
    assert daq.ambient == 40.0
    assert daq.gain == 2.0
    assert daq.tau >= 0.1            # tau borné à un minimum > 0
    assert daq.noise == 0.0
    c.close()


def test_sim_set_couplings_reinstalls(cfg):
    c = Controller(cfg)
    c.connect()
    new = [{"gate": "GATE", "drains": ["DRAIN"], "vth": -3.0, "gm": 0.5, "imax": 2.0}]
    c.sim_set_couplings(new)
    assert cfg.simulation["couplings"][0]["gm"] == 0.5
    c.close()


def test_sim_setters_noop_when_not_simulate(cfg):
    cfg.simulate = False
    c = Controller(cfg)
    c.sim_set_load("VLOAD", 3.0)
    c.sim_set_thermal(ambient_c=99.0)
    # La config n'est pas modifiée hors simulation.
    assert cfg.simulation["loads"]["VLOAD"] == 12.0   # valeur de la fixture, inchangée
    assert cfg.simulation["ambient_c"] == 25.0
