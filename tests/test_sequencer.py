"""Tests de l'analyse (parsing) des séquences."""

import pytest

from alim_seq.sequencer import (SequenceError, _expr_from_args, estimate_duration,
                                parse_sequence)

LABELS = {"VD", "VG1", "VG2", "VDD", "DRAIN"}
SENSORS = {"TS1"}


def parse(text):
    return parse_sequence(text, LABELS, SENSORS)


def test_parse_basic_commands_and_comments():
    seq = """
    # commentaire
    SET VD 24 0.5
    ON VD   // inline
    WAIT 1.0
    SETV VG2 = (VD/2)+VG1
    OFF VD
    """
    actions = parse(seq)
    assert [a.cmd for a in actions] == ["SET", "ON", "WAIT", "SETV", "OFF"]


def test_unknown_command_rejected():
    with pytest.raises(SequenceError):
        parse("FOO VD 1")


def test_servo_variants_parsed():
    actions = parse("SERVO_LIN VG1 VD 0.1\nSERVO_ADAPT VG1 VD 0.1 damping=0.5\nSERVO VG1 VD 0.1")
    assert [a.cmd for a in actions] == ["SERVO_LIN", "SERVO_ADAPT", "SERVO"]


def test_servo_unknown_measure_label_rejected():
    with pytest.raises(SequenceError):
        parse("SERVO_ADAPT VG1 NOPE 0.1")


def test_repeat_expands_and_nests():
    actions = parse("REPEAT 2\nON VD\nREPEAT 3\nWAIT 1\nEND\nOFF VD\nEND")
    cmds = [a.cmd for a in actions]
    # 2 × (ON + 3×WAIT + OFF) = 2×5 = 10 actions
    assert len(cmds) == 10
    assert cmds.count("WAIT") == 6 and cmds.count("ON") == 2 and cmds.count("OFF") == 2


def test_repeat_unbalanced_rejected():
    with pytest.raises(SequenceError):
        parse("REPEAT 2\nON VD")          # END manquant
    with pytest.raises(SequenceError):
        parse("ON VD\nEND")               # END orphelin
    with pytest.raises(SequenceError):
        parse("REPEAT 0\nON VD\nEND")     # compteur < 1


def test_estimate_duration():
    actions = parse("REPEAT 3\nWAIT 2\nRAMP VD 10 5\nEND\nWAIT 1")
    # 3 × (2 + 5) + 1 = 22 s
    assert estimate_duration(actions) == pytest.approx(22.0)


def test_unknown_label_rejected():
    with pytest.raises(SequenceError):
        parse("SET GHOST 1 1")


def test_setv_unknown_label_in_expr_rejected():
    with pytest.raises(SequenceError):
        parse("SETV VG2 = (VD/2)+GHOST")


def test_setv_unsafe_expr_rejected():
    with pytest.raises(SequenceError):
        parse("SETV VG2 = VD**2")


@pytest.mark.parametrize("line", [
    "RAMP VG1 -5 2.0",          # 3-arg : depuis valeur courante
    "RAMP VD 24 0 1.0",         # 4-arg : depart explicite
    "RAMP VD 24 0 1.0 50",      # 5-arg : avec pas
])
def test_ramp_forms_accepted(line):
    assert len(parse(line)) == 1


def test_ramp_too_few_args_rejected():
    with pytest.raises(SequenceError):
        parse("RAMP VG1 -5")


def test_wait_temp_unknown_sensor_rejected():
    with pytest.raises(SequenceError):
        parse("WAIT_TEMP GHOST < 50")


def test_expr_from_args_strips_equals():
    assert _expr_from_args(["=", "(VD/2)", "+", "VG1"]) == "(VD/2) + VG1"
    assert _expr_from_args(["(VD/2)+VG1"]) == "(VD/2)+VG1"


# --- T4 : validation numérique à l'analyse ---------------------------------
@pytest.mark.parametrize("line", [
    "SET VD abc 0.5",           # tension non numérique
    "SET VD 24 xx",             # courant non numérique
    "SET VD 24 -1",             # courant négatif
    "VOLTAGE VD douze",         # tension non numérique
    "CURRENT VD -0.1",          # courant négatif
    "WAIT deux",                # durée non numérique
    "WAIT -1",                  # durée négative
    "RAMP VD abc 1.0",          # Vfin non numérique (forme 3)
    "RAMP VD 0 24 zz",          # durée non numérique (forme 4)
    "RAMP VD 0 24 0",           # durée nulle refusée à l'analyse (positive)
    "SERVO_LIN VG1 VD notnum",  # courant cible non numérique
    "WAIT_CURRENT VD >= abc",   # valeur non numérique
    "WAIT_TEMP TS1 <= abc",     # valeur non numérique
])
def test_non_numeric_args_rejected(line):
    with pytest.raises(SequenceError):
        parse(line)


@pytest.mark.parametrize("line", [
    "RAMP VD 0 24 1.0 0.1",     # pas fractionnaire -> refusé
    "RAMP VD 0 24 1.0 1",       # 1 pas < 2 -> refusé
    "RAMP VD 0 24 1.0 abc",     # pas non entier
])
def test_ramp_steps_must_be_integer_ge_2(line):
    with pytest.raises(SequenceError) as exc:
        parse(line)
    assert "step" in str(exc.value).lower()


def test_ramp_steps_valid_integer_accepted():
    assert len(parse("RAMP VD 0 24 1.0 5")) == 1


@pytest.mark.parametrize("line", [
    "SERVO_LIN VG1 VD 0.1 gain=2",      # clé inconnue
    "SERVO_LIN VG1 VD 0.1 step=fast",   # valeur non numérique
    "SERVO_LIN VG1 VD 0.1 nokey",       # pas de '='
    "SERVO_ADAPT VG1 VD 0.1 wobble=1",  # clé inconnue
    "WAIT_CURRENT VD >= 1 delay=5",     # clé hors liste blanche
])
def test_kwargs_whitelist_enforced(line):
    with pytest.raises(SequenceError):
        parse(line)


def test_servo_adapt_damping_allowed():
    assert len(parse("SERVO_ADAPT VG1 VD 0.1 damping=0.5")) == 1


# --- T5 : progression + pas-à-pas (moteur SequenceRunner) ------------------
import time as _time


def _wait(cond, timeout=3.0):
    end = _time.monotonic() + timeout
    while _time.monotonic() < end:
        if cond():
            return True
        _time.sleep(0.01)
    return False


def _labels(ctrl):
    return set(ctrl.cfg.all_labels)


def test_runner_progress_counts_actions(ctrl):
    acts = parse_sequence("WAIT 0.02\nWAIT 0.02\nWAIT 0.02",
                          _labels(ctrl), set(ctrl.cfg.temperatures))
    r = ctrl.runner
    assert r.progress == (0, 0)
    r.start(acts)
    assert _wait(lambda: not r.is_running, 3)
    assert r.progress == (3, 3)          # index final = total


def test_step_mode_blocks_until_step_once(ctrl):
    acts = parse_sequence("ON D1\nON AUX", _labels(ctrl), set(ctrl.cfg.temperatures))
    r = ctrl.runner
    r.set_step_mode(True)
    r.start(acts)
    # Première action en attente : rien n'est exécuté sans autorisation.
    _time.sleep(0.15)
    assert ctrl.get_setpoint("D1").output is False
    r.step_once()                        # -> exécute ON D1
    assert _wait(lambda: ctrl.get_setpoint("D1").output, 2)
    # La 2ᵉ action reste bloquée tant qu'on n'autorise pas le pas suivant.
    _time.sleep(0.15)
    assert ctrl.get_setpoint("AUX").output is False
    r.step_once()                        # -> exécute ON AUX
    assert _wait(lambda: ctrl.get_setpoint("AUX").output, 2)
    assert _wait(lambda: not r.is_running, 2)


def test_step_mode_stop_interrupts_wait(ctrl):
    acts = parse_sequence("ON D1\nON AUX", _labels(ctrl), set(ctrl.cfg.temperatures))
    r = ctrl.runner
    r.set_step_mode(True)
    r.start(acts)
    _time.sleep(0.1)                     # bloqué en attente du 1er pas
    assert r.is_running
    assert r.stop() is True             # arrêt utilisateur pendant l'attente
    assert _wait(lambda: not r.is_running, 2)
    assert ctrl.get_setpoint("D1").output is False


def test_safety_mode_ignores_step_mode(ctrl):
    # Une désalimentation de sécurité ne doit JAMAIS attendre le pas-à-pas.
    ctrl.set_output("D1", True)
    acts = parse_sequence("OFF D1\nALL_OFF", _labels(ctrl), set(ctrl.cfg.temperatures))
    r = ctrl.runner
    r.set_step_mode(True)
    r.start(acts, safety_mode=True)     # pas de step_once() appelé
    assert _wait(lambda: not r.is_running, 3)
    assert ctrl.get_setpoint("D1").output is False
