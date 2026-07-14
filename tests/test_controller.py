"""Tests du contrôleur en simulation : polarité, groupes série, asservissement,
consignes calculées, validité/défaut capteurs, CV/CC, sécurité."""

import pytest

from alim_seq.controller import CRITICAL, FAULT, NA, OK


# --------------------------------------------------------------- polarité
def test_polarity_clamp_and_magnitude(ctrl):
    ctrl.set_voltage("GATE", -10)          # plage négative [-5, 0]
    assert ctrl.get_setpoint("GATE").set_voltage == pytest.approx(-5.0)
    ctrl.set_voltage("GATE", 3)            # positif interdit -> 0
    assert ctrl.get_setpoint("GATE").set_voltage == pytest.approx(0.0)
    ctrl.set_voltage("GATE", -2)
    psu, ch = ctrl._route("GATE")           # magnitude programmée positive
    assert psu._state[ch].set_voltage == pytest.approx(2.0)


def test_polarity_measure_sign(ctrl):
    ctrl.set_voltage("GATE", -2)
    ctrl.set_output("GATE", True)
    ctrl._meas_cycle()
    assert ctrl.snapshot().channels["GATE"].meas_voltage == pytest.approx(-2.0, abs=0.05)


# ------------------------------------------------------- groupes série
def test_group_split_equal(ctrl):
    ctrl.set_voltage("DRAIN", 10)
    assert ctrl.get_setpoint("D1").set_voltage == pytest.approx(5.0)
    assert ctrl.get_setpoint("D2").set_voltage == pytest.approx(5.0)


def test_group_clamped_to_group_max(ctrl):
    ctrl.set_voltage("DRAIN", 50)           # max groupe = 40 -> 20/20
    assert ctrl.get_setpoint("D1").set_voltage == pytest.approx(20.0)
    assert ctrl.get_setpoint("D2").set_voltage == pytest.approx(20.0)


def test_group_spillover():
    # max asymétriques -> débordement sur la voie la plus capable.
    from tests.conftest import build_config
    from alim_seq.controller import Controller
    cfg = build_config()
    cfg.channels["D1"].max_voltage = 5.0    # D1 plafonne à 5
    c = Controller(cfg); c.connect(); c.stop_polling()
    try:
        c.set_voltage("DRAIN", 20)          # 5 sur D1, 15 sur D2
        assert c.get_setpoint("D1").set_voltage == pytest.approx(5.0)
        assert c.get_setpoint("D2").set_voltage == pytest.approx(15.0)
    finally:
        c.close()


def test_group_current_common(ctrl):
    ctrl.set_current("DRAIN", 0.5)
    assert ctrl.get_setpoint("D1").set_current == pytest.approx(0.5)
    assert ctrl.get_setpoint("D2").set_current == pytest.approx(0.5)


def test_group_on_off_and_aggregate(ctrl):
    ctrl.set_current("DRAIN", 1.0)
    ctrl.set_voltage("DRAIN", 20)           # 10/10, grille OFF -> Id=0 -> CV
    ctrl.set_output("DRAIN", True)
    ctrl._meas_cycle()
    g = ctrl.snapshot().channels["DRAIN"]
    assert g.output is True
    assert g.meas_voltage == pytest.approx(20.0, abs=0.5)
    ctrl.set_output("DRAIN", False)
    assert ctrl.get_setpoint("D1").output is False
    assert ctrl.get_setpoint("D2").output is False


# ------------------------------------------------ asservissement + couplage
def test_servo_gate_drain_converges(ctrl):
    ctrl.set_current("DRAIN", 1.0)
    ctrl.set_voltage("DRAIN", 24)
    ctrl.set_output("DRAIN", True)
    ctrl.set_output("GATE", True)
    ok = ctrl.servo("GATE", "DRAIN", target_current=0.36,
                    step=0.05, tol=0.01, settle=0.01, timeout=10)
    assert ok is True
    i = ctrl._read_current("DRAIN")
    assert i == pytest.approx(0.36, abs=0.02)
    assert ctrl.get_setpoint("GATE").set_voltage < 0     # grille négative


def test_servo_adaptive_converges(ctrl):
    ctrl.set_current("DRAIN", 1.0)
    ctrl.set_voltage("DRAIN", 24)
    ctrl.set_output("DRAIN", True)
    ctrl.set_output("GATE", True)
    ok = ctrl.servo_adaptive("GATE", "DRAIN", target_current=0.36,
                             step=0.5, tol=0.01, settle=0.0, timeout=10)
    assert ok is True
    i = ctrl._read_current("DRAIN")
    assert i == pytest.approx(0.36, abs=0.02)
    assert ctrl.get_setpoint("GATE").set_voltage < 0


def test_servo_adaptive_fewer_steps_than_linear():
    # À précision égale, le pas adaptatif converge en bien moins d'écritures.
    from alim_seq.controller import Controller
    from tests.conftest import build_config

    def run_count(adaptive):
        c = Controller(build_config()); c.connect(); c.stop_polling()
        c.set_current("DRAIN", 1.0); c.set_voltage("DRAIN", 24)
        c.set_output("DRAIN", True); c.set_output("GATE", True)
        n = [0]; orig = c.set_voltage
        c.set_voltage = lambda lbl, v: (n.__setitem__(0, n[0] + 1), orig(lbl, v))[1]
        try:
            if adaptive:
                ok = c.servo_adaptive("GATE", "DRAIN", 0.36, step=0.5, tol=0.01,
                                      settle=0.0, timeout=10)
            else:
                ok = c.servo("GATE", "DRAIN", 0.36, step=0.02, tol=0.01,
                             settle=0.0, timeout=10)
            return ok, n[0]
        finally:
            c.close()

    ok_a, steps_a = run_count(True)
    ok_l, steps_l = run_count(False)
    assert ok_a and ok_l
    assert steps_a < steps_l
    assert steps_a <= 8


# -------------------------------------------------- consignes calculées
def test_eval_expression_signed(ctrl):
    ctrl.set_voltage("DRAIN", 24)
    ctrl.set_voltage("GATE", -2)
    assert ctrl.eval_expression("(DRAIN/2)+GATE") == pytest.approx(10.0)
    assert ctrl.eval_expression("(DRAIN/2)-GATE") == pytest.approx(14.0)


# ----------------------------------------------- validité / défaut capteurs
def test_sensor_requires_gating(ctrl):
    ctrl._temp_cycle()                       # VLOAD OFF -> capteur en attente
    assert ctrl.snapshot().temp_status["TS1"] == NA
    ctrl.set_output("VLOAD", True)
    ctrl._temp_cycle()
    assert ctrl.snapshot().temp_status["TS1"] != NA


def test_sensor_fault_out_of_range(ctrl):
    ctrl.set_output("VLOAD", True)
    ctrl._daq.read_temperatures = lambda: {"TS1": 999.0}
    ctrl._temp_cycle()
    assert ctrl.snapshot().temp_status["TS1"] == FAULT


def test_sensor_ref_voltage_fault(ctrl):
    # La voie VLOAD alimente le pont ; v_ref attendu = 6 V, tolérance 5 %.
    s = ctrl.cfg.temperatures["TS1"]
    s.ref_channel = "VLOAD"
    s.ref_tol = 0.05
    s.converter = {"type": "identity", "v_ref": 6.0}
    ctrl.set_voltage("VLOAD", 6.0)
    ctrl.set_output("VLOAD", True)
    ctrl._daq.read_temperatures = lambda: {"TS1": 30.0}
    ctrl._meas_cycle()                       # VLOAD mesuré ~6 V
    ctrl._temp_cycle()
    assert ctrl.snapshot().temp_status["TS1"] == OK   # référence correcte

    ctrl.set_voltage("VLOAD", 3.0)           # référence chute -> -50 %
    ctrl._meas_cycle()
    ctrl._temp_cycle()
    assert ctrl.snapshot().temp_status["TS1"] == FAULT


def test_sensor_ref_voltage_explicit_for_table(ctrl):
    # Convertisseur 'table' (sans v_ref) : la Vref attendue vient de ref_voltage.
    s = ctrl.cfg.temperatures["TS1"]
    s.ref_channel = "VLOAD"
    s.ref_voltage = 6.0
    s.converter = {"type": "table", "points": [[0.0, 100.0], [10.0, 0.0]]}
    assert s.expected_vref == 6.0
    ctrl.set_voltage("VLOAD", 6.0); ctrl.set_output("VLOAD", True)
    ctrl._daq.read_temperatures = lambda: {"TS1": 30.0}
    ctrl._meas_cycle(); ctrl._temp_cycle()
    assert ctrl.snapshot().temp_status["TS1"] == OK
    ctrl.set_voltage("VLOAD", 4.0); ctrl._meas_cycle(); ctrl._temp_cycle()
    assert ctrl.snapshot().temp_status["TS1"] == FAULT


# ----------------------------------------------------------- CV/CC
def test_cv_then_cc_inference(ctrl):
    ctrl.set_voltage("VLOAD", 6)
    ctrl.set_current("VLOAD", 1.0)           # 6V/12ohm = 0.5A < 1A -> CV
    ctrl.set_output("VLOAD", True)
    ctrl._meas_cycle()
    assert ctrl.snapshot().channels["VLOAD"].mode == "CV"
    ctrl.set_current("VLOAD", 0.1)           # 0.5A > 0.1A -> CC
    ctrl._meas_cycle(); ctrl._meas_cycle()
    assert ctrl.snapshot().channels["VLOAD"].mode == "CC"


# ----------------------------------------------------------- sécurité
def test_hard_cut_emergency(ctrl):
    ctrl.set_output("VLOAD", True)           # capteur prêt
    ctrl.set_output("D1", True)
    # 120°C : critique (>= 80+15) ET dans la plage plausible (<= 150) -> coupure dure.
    ctrl._daq.read_temperatures = lambda: {"TS1": 120.0}
    ctrl._temp_cycle()
    assert ctrl.tripped is True
    assert ctrl._hard_cut_done is True
    assert ctrl.get_setpoint("D1").output is False


def test_critical_does_not_trip_when_sensor_not_ready(ctrl):
    # VLOAD OFF -> TS1 « en attente » : une temp critique est ignorée.
    ctrl.set_output("D1", True)
    ctrl._daq.read_temperatures = lambda: {"TS1": 200.0}
    ctrl._temp_cycle()
    assert ctrl.tripped is False
    assert ctrl.get_setpoint("D1").output is True


def test_comm_lost_temperature_triggers(ctrl):
    ctrl.set_output("D1", True)
    ctrl._daq_fail = ctrl.cfg.safety["comm_fail_limit"]
    ctrl._handle_temp_failure()
    assert ctrl.comm_lost is True


def test_no_temperature_monitoring(cfg):
    # 'temperatures' vide -> pas de boucle température, module NI non utilisé.
    cfg.temperatures = {}
    from alim_seq.controller import Controller
    c = Controller(cfg)
    assert c._temp_enabled is False
    assert c.connect() is True
    c.set_output("D1", True)
    snap = c.snapshot()
    assert snap.temperatures == {} and snap.safety_status == OK and not snap.tripped
    assert not (c._temp_thread and c._temp_thread.is_alive())
    c.close()


def test_runner_pause_freezes_then_resumes(ctrl):
    import time
    from alim_seq.sequencer import parse_sequence
    acts = parse_sequence("WAIT 0.3\nON D1",
                          set(ctrl.cfg.all_labels), set(ctrl.cfg.temperatures))
    ctrl.runner.start(acts)
    time.sleep(0.05)
    ctrl.runner.pause()
    time.sleep(0.5)                       # le WAIT 0.3 est gelé tant qu'on est en pause
    assert ctrl.runner.is_running and ctrl.runner.is_paused
    assert ctrl.get_setpoint("D1").output is False
    ctrl.runner.resume()
    time.sleep(0.6)
    assert ctrl.get_setpoint("D1").output is True


def test_reconnect_clears_comm_lost(ctrl):
    ctrl._comm_lost = True
    assert ctrl.reconnect() is True
    assert ctrl.comm_lost is False


def test_auto_reconnect_watchdog_lifecycle(cfg):
    from alim_seq.controller import Controller
    cfg.safety["auto_reconnect"] = True
    c = Controller(cfg)
    assert c.connect() is True
    assert c._wd_thread is not None and c._wd_thread.is_alive()
    c.close()
    assert not c._wd_thread.is_alive()


def test_connect_failure_is_graceful(cfg):
    from alim_seq.controller import Controller
    c = Controller(cfg)
    c._daq.connect = lambda: (_ for _ in ()).throw(RuntimeError("NI absent"))
    assert c.connect() is False
    assert c.connected is False
    assert "NI" in c.connect_error
    c.close()


def test_sequence_refusee_si_non_connecte(ctrl):
    """Matériel non connecté (mode réel sans banc, ou perte de comm) : une séquence
    utilisateur est refusée sans démarrer le runner ni un enregistrement."""
    ctrl._comm_lost = True
    ctrl.drain_logs()
    ctrl.start_user_sequence([])
    assert ctrl.runner.is_running is False
    assert ctrl.essai is None
    assert any("not connected" in line for line in ctrl.drain_logs())


def test_sequence_refusee_si_deconnecte(ctrl):
    ctrl._connected = False
    ctrl.drain_logs()
    ctrl.start_user_sequence([])
    assert ctrl.runner.is_running is False
    assert any("not connected" in line for line in ctrl.drain_logs())
