"""Tests de chargement / validation de la configuration."""

import json

import pytest

from alim_seq.config import load_config

_BASE = {
    "simulate": True,
    "supplies": {"PSU1": {"resource": "x"}},
    "channels": {"A": {"supply": "PSU1", "channel": 1, "warning": 1}},
    "temperatures": {},
    "safety": {},
}


def _write(tmp_path, raw):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


def test_load_valid(tmp_path):
    cfg = load_config(_write(tmp_path, _BASE))
    assert cfg.simulate is True
    assert cfg.channels["A"].polarity == 1.0


def test_source_path_set_and_resolved(tmp_path):
    p = _write(tmp_path, _BASE)
    cfg = load_config(p)
    assert cfg.source_path == p.resolve()
    assert cfg.source_path.is_absolute()


def test_source_path_none_for_code_built_config():
    from alim_seq.config import AppConfig
    cfg = AppConfig(simulate=True, supplies={}, channels={}, temperatures={},
                    daq={}, safety={})
    assert cfg.source_path is None


# --- Section unifiée 'instruments' (phase 3, docs/DESIGN_INSTRUMENTS.md) ---------
def test_legacy_supplies_daq_derive_instruments(tmp_path):
    """Une config héritée (supplies+daq) produit une section 'instruments' cohérente."""
    raw = json.loads(json.dumps(_BASE))
    raw["supplies"]["PSU1"] = {"model": "HMP2020", "resource": "x"}
    raw["daq"] = {"device": "Dev1"}
    cfg = load_config(_write(tmp_path, raw))
    assert cfg.instruments["PSU1"] == {"driver": "HMP2020", "resource": "x"}
    # Un instrument de température (driver NI-DAQ) est dérivé.
    temp = [n for n, e in cfg.instruments.items() if e["driver"] == "NI-DAQ"]
    assert len(temp) == 1


def test_supplies_and_relay_instruments_coexist(tmp_path):
    """Sources en 'supplies' (legacy) + relais en 'instruments' : rien n'est perdu."""
    raw = json.loads(json.dumps(_BASE))  # a supplies PSU1
    raw["instruments"] = {"RLY": {"driver": "MOCK-RELAY", "outputs": ["K1", "K2"]}}
    cfg = load_config(_write(tmp_path, raw))
    assert "PSU1" in cfg.instruments          # source legacy préservée
    assert "RLY" in cfg.instruments           # relais ajouté
    assert cfg.supplies == {"PSU1": {"model": "HMP4040", "resource": "x"}}
    assert set(cfg.relay_labels) == {"K1", "K2"}


def test_relay_not_derived_as_daq(tmp_path):
    """Un relais (actionneur) ne doit pas être pris pour le module de température."""
    raw = json.loads(json.dumps(_BASE))
    raw["instruments"] = {"RLY": {"driver": "MOCK-RELAY", "outputs": ["K1"]}}
    cfg = load_config(_write(tmp_path, raw))
    assert "RLY" not in str(cfg.daq)          # pas déversé dans daq
    assert "RLY" not in cfg.supplies          # ni dans supplies
    assert cfg.relay_labels == ["K1"]


def test_native_instruments_config(tmp_path):
    """Une config décrite via 'instruments' (sans supplies/daq) charge et dérive le sucre."""
    raw = json.loads(json.dumps(_BASE))
    del raw["supplies"]
    raw["instruments"] = {
        "P": {"driver": "HMP4040", "resource": "y"},
        "NI": {"driver": "NI-DAQ", "device": "Dev2"},
    }
    raw["channels"]["A"]["supply"] = "P"
    cfg = load_config(_write(tmp_path, raw))
    assert cfg.supplies == {"P": {"model": "HMP4040", "resource": "y"}}
    assert cfg.daq.get("device") == "Dev2"


def test_instruments_round_trip(tmp_path):
    """config_to_dict recharge à l'identique (instruments fait foi)."""
    from alim_seq.config import config_to_dict
    cfg = load_config(_write(tmp_path, _BASE))
    p2 = tmp_path / "rt.json"
    p2.write_text(json.dumps(config_to_dict(cfg)), encoding="utf-8")
    cfg2 = load_config(p2)
    assert cfg2.instruments == cfg.instruments
    assert cfg2.supplies == cfg.supplies


def test_unknown_instrument_driver_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    del raw["supplies"]
    raw["instruments"] = {"X": {"driver": "ACME9000"}}
    raw["channels"]["A"]["supply"] = "X"
    with pytest.raises(ValueError, match="driver"):
        load_config(_write(tmp_path, raw))


def test_two_temperature_instruments_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    del raw["supplies"]
    raw["instruments"] = {
        "P": {"driver": "HMP4040"},
        "NI1": {"driver": "NI-DAQ"},
        "NI2": {"driver": "NI-DAQ"},
    }
    raw["channels"]["A"]["supply"] = "P"
    with pytest.raises(ValueError, match="température"):
        load_config(_write(tmp_path, raw))


def test_negative_polarity_parsed(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["channels"]["A"]["negative"] = True
    cfg = load_config(_write(tmp_path, raw))
    assert cfg.channels["A"].polarity == -1.0


def test_unknown_supply_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["channels"]["A"]["supply"] = "NOPE"
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, raw))


def test_channel_out_of_range_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["channels"]["A"]["channel"] = 9
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, raw))


def test_duplicate_physical_channel_rejected(tmp_path):
    # Deux voies ne peuvent pas pointer le même canal physique (alim+canal).
    raw = json.loads(json.dumps(_BASE))
    raw["channels"]["B"] = {"supply": "PSU1", "channel": 1, "warning": 1}
    with pytest.raises(ValueError, match="déjà affecté"):
        load_config(_write(tmp_path, raw))


def test_unknown_supply_model_rejected(tmp_path):
    # Un modèle d'alim inconnu est rejeté (désormais via la validation 'driver' de
    # la section unifiée 'instruments', modèle et driver étant synonymes pour une source).
    raw = json.loads(json.dumps(_BASE))
    raw["supplies"]["PSU1"]["model"] = "ACME9000"
    with pytest.raises(ValueError, match="driver|modèle"):
        load_config(_write(tmp_path, raw))


def test_channel_beyond_model_channels_rejected(tmp_path):
    # HMP2020 = 2 voies : un canal 3 doit être refusé (validation par modèle).
    raw = json.loads(json.dumps(_BASE))
    raw["supplies"]["PSU1"]["model"] = "HMP2020"
    raw["channels"]["A"]["channel"] = 3
    with pytest.raises(ValueError, match="hors plage"):
        load_config(_write(tmp_path, raw))


def test_soa_max_voltage_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["channels"]["A"]["max_voltage"] = 40          # > 32 V (HMP4040)
    with pytest.raises(ValueError, match="max_voltage"):
        load_config(_write(tmp_path, raw))


def test_soa_max_current_per_model_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["supplies"]["PSU1"]["model"] = "HMP2030"      # 5 A/voie
    raw["channels"]["A"]["max_current"] = 8           # > 5 A
    with pytest.raises(ValueError, match="max_current"):
        load_config(_write(tmp_path, raw))


def test_sensor_ref_channel_parsed_and_validated(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    # Convertisseur COMPLET : depuis l'analyse critique, la validation construit le
    # convertisseur dès le chargement (un dict incomplet est refusé — voulu).
    raw["temperatures"]["T"] = {
        "channel": "ai0", "warning": 60, "critical": 80,
        "converter": {"type": "ntc", "v_ref": 3.3, "r_series": 10000,
                      "r0": 10000, "t0": 25, "beta": 3950},
        "ref_channel": "A", "ref_tol": 0.1,
    }
    cfg = load_config(_write(tmp_path, raw))
    assert cfg.temperatures["T"].ref_channel == "A"
    assert cfg.temperatures["T"].ref_tol == 0.1
    # ref_channel inconnu -> refus
    raw["temperatures"]["T"]["ref_channel"] = "NOPE"
    with pytest.raises(ValueError, match="ref_channel"):
        load_config(_write(tmp_path, raw))
    # ref_channel sans aucune Vref attendue -> refus
    raw["temperatures"]["T"]["ref_channel"] = "A"
    raw["temperatures"]["T"]["converter"] = {"type": "identity"}
    raw["temperatures"]["T"].pop("ref_voltage", None)
    with pytest.raises(ValueError, match="référence attendue"):
        load_config(_write(tmp_path, raw))
    # mais 'ref_voltage' explicite (ex. convertisseur table) -> accepté
    raw["temperatures"]["T"]["converter"] = {"type": "table", "points": [[0, 0], [1, 1]]}
    raw["temperatures"]["T"]["ref_voltage"] = 5.0
    cfg2 = load_config(_write(tmp_path, raw))
    assert cfg2.temperatures["T"].expected_vref == 5.0


def test_ntc_without_fault_guard_rejected(tmp_path):
    # NTC sans plage plausible ET fault_margin=0 -> aucun garde-fou débranchement.
    raw = json.loads(json.dumps(_BASE))
    raw["temperatures"]["T"] = {
        "channel": "ai0", "warning": 60, "critical": 80,
        "converter": {"type": "ntc", "v_ref": 3.3, "r_series": 10000,
                      "r0": 10000, "t0": 25, "beta": 3950, "fault_margin": 0},
    }
    with pytest.raises(ValueError, match="débranchement"):
        load_config(_write(tmp_path, raw))
    # Avec une plage plausible, c'est accepté même si fault_margin=0.
    raw["temperatures"]["T"]["valid_min"] = -40
    raw["temperatures"]["T"]["valid_max"] = 150
    cfg = load_config(_write(tmp_path, raw))
    assert cfg.temperatures["T"].valid_max == 150


def test_group_unknown_member_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["channels"]["B"] = {"supply": "PSU1", "channel": 2}
    raw["groups"] = {"G": {"members": ["A", "NOPE"]}}
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, raw))


def test_sensor_thresholds_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["temperatures"] = {"T": {"channel": "ai0", "warning": 80, "critical": 60}}
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, raw))


def test_sensor_requires_unknown_rejected(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["temperatures"] = {"T": {"channel": "ai0", "warning": 60, "critical": 80,
                                 "requires": ["GHOST"]}}
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, raw))
