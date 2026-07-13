"""Tests de la couche multi-modèles d'alimentations (registre + fabrique)."""

import pytest

from alim_seq.psu import (HMP2030, MockPSU, available_models, create_psu,
                          psu_channel_count)


def test_registry_and_channel_counts():
    models = available_models()
    assert {"HMP4040", "HMP4030", "HMP2030", "HMP2020"} <= set(models)
    assert psu_channel_count("HMP4040") == 4
    assert psu_channel_count("hmp2020") == 2      # insensible à la casse
    assert psu_channel_count("inconnu") == 0


def test_create_simulated_psu_matches_model_channels():
    p = create_psu("HMP2020", simulate=True, name="X")
    assert isinstance(p, MockPSU)
    assert p.n_channels == 2
    assert set(p._state) == {1, 2}


def test_create_real_psu_returns_model_class():
    p = create_psu("HMP2030", resource="TCPIP::x::INSTR", simulate=False)
    assert isinstance(p, HMP2030)
    assert p.n_channels == 3


def test_unknown_model_raises():
    with pytest.raises(ValueError, match="inconnu"):
        create_psu("ACME9000", simulate=True)
