"""Sécurité : la désalimentation ordonnée ne laisse JAMAIS la carte alimentée
(séquence bloquée, runner.start qui lève, timeout) -> coupure dure en repli."""

import time

from alim_seq.sequencer import parse_sequence


def _wait(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def _labels(ctrl):
    return set(ctrl.cfg.all_labels)


def test_shutdown_normal_turns_all_off(ctrl):
    ctrl.cfg.safety["shutdown_delay"] = 0.0
    ctrl.set_output("D1", True)
    ctrl.set_output("VLOAD", True)
    ctrl.start_shutdown_sequence(trip=True)
    assert _wait(lambda: not ctrl._shutdown_inflight.is_set())
    assert ctrl.get_setpoint("D1").output is False
    assert ctrl.get_setpoint("VLOAD").output is False
    assert ctrl.tripped is True


def test_shutdown_hard_cut_when_user_sequence_stuck(ctrl, monkeypatch):
    # Séquence utilisateur qui refuse de s'arrêter : stop() neutralisé.
    ctrl.cfg.safety["shutdown_takeover_wait_s"] = 0.2
    ctrl.set_output("D1", True)
    ctrl.set_output("VLOAD", True)
    ctrl.runner.start(parse_sequence("WAIT 5", _labels(ctrl), set(ctrl.cfg.temperatures)))
    monkeypatch.setattr(ctrl.runner, "stop", lambda: None)

    ctrl.start_shutdown_sequence(reason="test", trip=True)
    assert _wait(lambda: not ctrl._shutdown_inflight.is_set())
    assert ctrl.tripped is True
    assert ctrl.get_setpoint("D1").output is False       # coupure dure de repli
    assert ctrl.get_setpoint("VLOAD").output is False


def test_shutdown_hard_cut_when_runner_start_raises(ctrl, monkeypatch):
    ctrl.set_output("D1", True)

    def _raise(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ctrl.runner, "start", _raise)
    ctrl.start_shutdown_sequence(reason="test", trip=False)
    assert _wait(lambda: not ctrl._shutdown_inflight.is_set())
    assert ctrl.get_setpoint("D1").output is False       # repli emergency_stop
    assert ctrl.tripped is True


def test_stop_sequence_refused_during_safety_shutdown(ctrl):
    # Un clic « Stop » pendant une désalim de sécurité doit être REFUSÉ, et la
    # désalim aller au bout (toutes voies OFF).
    ctrl.cfg.safety["shutdown_delay"] = 0.15
    for lbl in ("D1", "D2", "VLOAD"):
        ctrl.set_output(lbl, True)
    ctrl.start_shutdown_sequence(trip=True)
    refused = None
    for _ in range(200):
        if ctrl.runner.is_running and ctrl.runner._safety_mode:
            refused = ctrl.runner.stop()
            break
        time.sleep(0.01)
    assert refused is False                              # stop ignoré en safety_mode
    assert _wait(lambda: not ctrl._shutdown_inflight.is_set())
    for lbl in ("D1", "D2", "VLOAD"):
        assert ctrl.get_setpoint(lbl).output is False
    assert ctrl.tripped is True


def test_emergency_stop_interrupts_safety_shutdown(ctrl):
    ctrl.cfg.safety["shutdown_delay"] = 0.3
    for lbl in ("D1", "D2", "VLOAD"):
        ctrl.set_output(lbl, True)
    ctrl.start_shutdown_sequence(trip=True)
    assert _wait(lambda: ctrl.runner.is_running and ctrl.runner._safety_mode, 2)
    ctrl.emergency_stop("test urgence")                  # force_stop -> interrompt
    assert _wait(lambda: not ctrl.runner.is_running, 2)
    for lbl in ("D1", "D2", "VLOAD"):
        assert ctrl.get_setpoint(lbl).output is False
    assert ctrl.tripped is True and ctrl._hard_cut_done is True


def test_user_stop_normal_sequence_still_works(ctrl):
    acts = parse_sequence("ON D1\nWAIT 5", _labels(ctrl), set(ctrl.cfg.temperatures))
    ctrl.runner.start(acts)
    assert _wait(lambda: ctrl.get_setpoint("D1").output, 2)
    assert ctrl.runner.stop() is True                    # accepté hors safety_mode
    assert _wait(lambda: not ctrl.runner.is_running, 2)


def test_shutdown_hard_cut_on_timeout(ctrl):
    # Budget de désalimentation minuscule -> coupure dure si ça traîne.
    ctrl.cfg.safety["shutdown_timeout"] = 0.0
    ctrl.cfg.safety["shutdown_delay"] = 5.0              # extinction "lente"
    ctrl.set_output("D1", True)
    ctrl.start_shutdown_sequence(trip=True)
    assert _wait(lambda: not ctrl._shutdown_inflight.is_set())
    assert ctrl.get_setpoint("D1").output is False
    assert ctrl.tripped is True
