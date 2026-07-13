"""T6 : correctifs concurrence / cycle de vie.

- limite de courant de GROUPE réellement appliquée (GroupConfig.max_current) ;
- SequenceRunner.start() ne peut pas démarrer deux séquences (TOCTOU fermé) ;
- HMP4040.close() coupe les sorties avec un timeout court et sans *OPC?, puis
  restaure l'état et ferme la session même si l'alim ne répond plus.
"""

import pytest

from alim_seq.psu import HMP4040
from alim_seq.sequencer import parse_sequence


def test_group_max_current_clamped(ctrl):
    # Cap du groupe (0.4 A) plus bas que celui des membres (1.0 A) : une demande
    # à 5 A doit être bornée à 0.4 A sur chaque voie membre.
    ctrl.cfg.groups["DRAIN"].max_current = 0.4
    ctrl.set_current("DRAIN", 5.0)
    assert ctrl.get_setpoint("D1").set_current == pytest.approx(0.4)
    assert ctrl.get_setpoint("D2").set_current == pytest.approx(0.4)


def test_group_max_current_defaults_to_member_min(ctrl):
    # max_current=0 -> plus petit des max_current des membres (D1/D2 = 1.0 A).
    ctrl.cfg.groups["DRAIN"].max_current = 0.0
    ctrl.set_current("DRAIN", 5.0)
    assert ctrl.get_setpoint("D1").set_current == pytest.approx(1.0)


def test_runner_rejects_second_start(ctrl):
    acts = parse_sequence("WAIT 5", set(ctrl.cfg.all_labels), set(ctrl.cfg.temperatures))
    ctrl.runner.start(acts)
    try:
        with pytest.raises(RuntimeError):
            ctrl.runner.start(acts)          # déjà en cours -> refus
    finally:
        ctrl.runner.force_stop()


class _FakeVisa:
    """Instrument VISA factice : mémorise timeout, commandes et clôture."""

    def __init__(self):
        self.timeout = 5000
        self.timeouts_seen = []
        self.writes = []
        self.closed = False

    def write(self, cmd):
        # Photographie le timeout au moment de chaque écriture d'extinction.
        self.timeouts_seen.append(self.timeout)
        self.writes.append(cmd)

    def query(self, cmd):
        raise AssertionError("close() ne doit pas interroger *OPC? (use_opc off)")

    def close(self):
        self.closed = True


# --- T7 : robustesse des servos au bruit -----------------------------------
def test_read_current_median_rejects_outlier(ctrl, monkeypatch):
    # Séquence bruitée avec une valeur aberrante : la médiane l'écarte.
    seq = iter([0.30, 5.00, 0.32])       # 5.00 = pic de bruit
    monkeypatch.setattr(ctrl, "_read_current", lambda label: next(seq))
    assert ctrl._read_current_median("DRAIN", n=3) == pytest.approx(0.32)


def test_read_current_median_n1_single_read(ctrl, monkeypatch):
    monkeypatch.setattr(ctrl, "_read_current", lambda label: 0.5)
    assert ctrl._read_current_median("DRAIN", n=1) == 0.5


def test_servo_adaptive_still_converges_with_noise(ctrl):
    # Le servo adaptatif doit converger malgré le bruit (médiane + rejet de pente
    # sous le plancher de bruit) : cas nominal grille->drain.
    ctrl.set_current("DRAIN", 1.0)
    ctrl.set_voltage("DRAIN", 24)
    ctrl.set_output("DRAIN", True)
    ctrl.set_output("GATE", True)
    ok = ctrl.servo_adaptive("GATE", "DRAIN", target_current=0.36,
                             step=0.5, tol=0.01, settle=0.0, timeout=10)
    assert ok is True
    assert ctrl._read_current_median("DRAIN") == pytest.approx(0.36, abs=0.02)


def test_hmp4040_close_fast_and_no_opc():
    psu = HMP4040("TCPIP::x::INSTR", use_opc=True)
    fake = _FakeVisa()
    psu._inst = fake
    psu.use_opc = True

    psu.close()

    # Sorties coupées (une commande OUTP:SEL OFF par voie), avec un timeout court
    # et SANS *OPC? (sinon query() aurait levé). Session fermée, use_opc restauré.
    assert fake.closed is True
    assert psu._inst is None
    assert any("OUTP:SEL OFF" in w for w in fake.writes)
    assert fake.timeouts_seen and max(fake.timeouts_seen) <= 1000
    assert psu.use_opc is True                # restauré après extinction
