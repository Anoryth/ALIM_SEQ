"""Relais (capacité Actionneur) : sorties par label, safe_state, désalimentation."""

import json

import pytest

from alim_seq.config import load_config
from alim_seq.controller import Controller
from alim_seq.instrument import Actionneur, MesureTemperature, SourceTension, create_instrument
from alim_seq.relay import MockRelay
from alim_seq.sequencer import Action, SequenceError, parse_sequence


def _write(tmp_path, raw):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


_CFG = {
    "simulate": True,
    "instruments": {
        "PSU1": {"driver": "HMP4040"},
        "TEMP": {"driver": "NI-DAQ"},
        "RLY": {"driver": "MOCK-RELAY",
                "outputs": {"K1": {"safe_state": False}, "K2": {"safe_state": True}}},
    },
    "channels": {"A": {"supply": "PSU1", "channel": 1,
                       "max_voltage": 10, "max_current": 2}},
    "temperatures": {},
    "safety": {},
}


def _ctrl(tmp_path):
    c = Controller(load_config(_write(tmp_path, _CFG)))
    assert c.connect()
    return c


# --- driver ---------------------------------------------------------------------
def test_mockrelay_capabilities():
    r = MockRelay(name="RLY", outputs=["K1", "K2"])
    assert isinstance(r, Actionneur)
    assert not isinstance(r, (SourceTension, MesureTemperature))
    assert r.states() == {"K1": False, "K2": False}
    r.set_state("K1", True)
    assert r.get_state("K1") is True
    r.all_off()
    assert r.states() == {"K1": False, "K2": False}
    with pytest.raises(KeyError):
        r.set_state("NOPE", True)


def test_create_instrument_relay():
    inst = create_instrument("MOCK-RELAY", simulate=True, name="RLY", outputs=["K1"])
    assert isinstance(inst, MockRelay)
    assert isinstance(inst, Actionneur)
    assert inst.outputs == ["K1"]


# --- config ---------------------------------------------------------------------
def test_relay_labels_and_map(tmp_path):
    cfg = load_config(_write(tmp_path, _CFG))
    assert set(cfg.relay_labels) == {"K1", "K2"}
    assert cfg.relay_map["K2"]["instrument"] == "RLY"
    assert cfg.relay_map["K2"]["safe_state"] is True


def test_relay_label_collision_rejected(tmp_path):
    raw = json.loads(json.dumps(_CFG))
    raw["instruments"]["RLY"]["outputs"] = ["A"]  # collision avec la voie "A"
    with pytest.raises(ValueError, match="conflicts"):
        load_config(_write(tmp_path, raw))


# --- contrôleur -----------------------------------------------------------------
def test_controller_set_and_read_relay(tmp_path):
    c = _ctrl(tmp_path)
    assert c.relay_state("K1") is False
    c.set_relay("K1", True)
    assert c.relay_state("K1") is True
    assert c.snapshot().relays == {"K1": True, "K2": False}
    c.close()


def test_relay_on_refused_when_tripped(tmp_path):
    c = _ctrl(tmp_path)
    c.emergency_stop("test")
    assert c.tripped
    c.set_relay("K1", True)          # refusé tant que trippé
    assert c.relay_state("K1") is False
    c.close()


def test_emergency_drives_relays_to_safe_state(tmp_path):
    c = _ctrl(tmp_path)
    c.set_relay("K1", True)          # K1 safe_state=False
    c.set_relay("K2", False)         # K2 safe_state=True
    c.emergency_stop("test")
    assert c.relay_state("K1") is False   # ramené à l'état de sécurité
    assert c.relay_state("K2") is True
    c.close()


# --- séquenceur -----------------------------------------------------------------
def test_sequence_relay_validation(tmp_path):
    cfg = load_config(_write(tmp_path, _CFG))
    relays = set(cfg.relay_labels)
    # OK
    acts = parse_sequence("RELAY K1 ON\nRELAY K2 OFF", set(cfg.all_labels),
                          set(cfg.temperatures), relays)
    assert [a.cmd for a in acts] == ["RELAY", "RELAY"]
    # sortie inconnue
    with pytest.raises(SequenceError, match="relay output"):
        parse_sequence("RELAY NOPE ON", set(cfg.all_labels), set(cfg.temperatures), relays)
    # état invalide
    with pytest.raises(SequenceError, match="ON or OFF"):
        parse_sequence("RELAY K1 MAYBE", set(cfg.all_labels), set(cfg.temperatures), relays)


def test_sequence_relay_execute(tmp_path):
    c = _ctrl(tmp_path)
    ok = c.runner._execute(Action(lineno=1, cmd="RELAY", args=["K1", "ON"], raw="RELAY K1 ON"))
    assert ok and c.relay_state("K1") is True
    c.close()
