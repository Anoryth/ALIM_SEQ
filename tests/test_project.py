"""Garde-fous sur les artefacts livrés (config.json + séquences réelles)."""

from pathlib import Path

from alim_seq.config import load_config
from alim_seq.sequencer import parse_sequence

ROOT = Path(__file__).resolve().parent.parent


def test_shipped_config_is_valid():
    # Config neutre livrée par défaut : démarre en simulation, voies génériques,
    # pas de capteur de température (l'utilisateur les ajoute pour son banc).
    cfg = load_config(ROOT / "config.json")
    assert cfg.simulate is True
    assert cfg.channels
    assert cfg.supplies


def test_shipped_sequences_parse():
    cfg = load_config(ROOT / "config.json")
    labels = set(cfg.all_labels)
    sensors = set(cfg.temperatures)
    relays = set(cfg.relay_labels)
    files = list((ROOT / "sequences").glob("*.seq"))
    assert files, "aucune séquence trouvée"
    for p in files:
        parse_sequence(p.read_text(encoding="utf-8"), labels, sensors, relays)


def test_snapshot_exposes_cadence():
    from alim_seq.controller import Controller
    cfg = load_config(ROOT / "config.json")
    c = Controller(cfg)
    c.connect()
    snap = c.snapshot()
    assert hasattr(snap, "meas_period") and hasattr(snap, "temp_period")
    c.close()
