"""Abstraction des appareils par capacités (cf. docs/ARCHITECTURE.md §5).

On vérifie que les drivers existants exposent les bonnes capacités, que le registre
unifié / la fabrique fonctionnent, et surtout que la parité simulation est préservée.
"""

import math

import pytest

from alim_seq.config import TempSensorConfig
from alim_seq.daq import BaseDAQ, MockDAQ, NIDaq
from alim_seq.instrument import (
    Actionneur,
    Instrument,
    MesureTemperature,
    MesureVI,
    SourceTension,
    available_instruments,
    capabilities_of,
    create_instrument,
)
from alim_seq.psu import HMP4040, BasePSU, MockPSU


def test_alim_expose_source_et_mesure_vi():
    psu = MockPSU(n_channels=4)
    assert isinstance(psu, Instrument)
    assert isinstance(psu, SourceTension)
    assert isinstance(psu, MesureVI)
    # Une alim n'est PAS un capteur de température ni un actionneur.
    assert not isinstance(psu, MesureTemperature)
    assert not isinstance(psu, Actionneur)
    assert set(capabilities_of(psu)) == {"SourceTension", "MesureVI"}


def test_hmp_classe_reelle_expose_les_memes_capacites():
    # Sans instancier (pas de VISA) : les capacités sont portées par la classe.
    assert issubclass(HMP4040, SourceTension)
    assert issubclass(HMP4040, MesureVI)
    assert issubclass(BasePSU, Instrument)


def test_daq_expose_mesure_temperature():
    sensors = {"T1": TempSensorConfig(name="T1", channel="ai0",
                                      converter={"type": "identity"},
                                      warning=60.0, critical=80.0)}
    daq = MockDAQ(sensors=sensors, power_provider=lambda: 0.0)
    assert isinstance(daq, Instrument)
    assert isinstance(daq, MesureTemperature)
    assert not isinstance(daq, SourceTension)
    assert capabilities_of(daq) == ["MesureTemperature"]
    assert issubclass(NIDaq, MesureTemperature)


def test_registre_liste_sources_et_temperature():
    dispo = available_instruments()
    assert "HMP4040" in dispo      # source via PSU_MODELS
    assert "NI-DAQ" in dispo       # température


def test_fabrique_source_parite_simulation():
    # En simulation, un driver de source réel produit un mock équivalent.
    inst = create_instrument("HMP4040", simulate=True, name="PSU_A")
    assert isinstance(inst, MockPSU)
    assert isinstance(inst, SourceTension)
    assert inst.n_channels == 4  # nombre de voies du modèle demandé


def test_fabrique_temperature_simulation():
    sensors = {"T1": TempSensorConfig(name="T1", channel="ai0",
                                      converter={"type": "identity"},
                                      warning=60.0, critical=80.0)}
    daq = create_instrument("NI-DAQ", simulate=True, name="TEMP",
                            sensors=sensors, power_provider=lambda: 10.0,
                            ambient_c=25.0)
    assert isinstance(daq, MockDAQ)
    assert daq.name == "TEMP"
    daq.connect()
    temps = daq.read_temperatures()
    assert set(temps) == {"T1"}
    assert not math.isnan(temps["T1"])


def test_fabrique_temperature_requiert_sensors():
    with pytest.raises(ValueError):
        create_instrument("NI-DAQ", simulate=True)


def test_fabrique_driver_inconnu():
    with pytest.raises(ValueError):
        create_instrument("PAS_UN_DRIVER", simulate=True)
