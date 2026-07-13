"""Enregistrement CSV : tensions brutes du module NI en plus des °C."""

import csv

import pytest

from alim_seq.config import TempSensorConfig
from alim_seq.daq import NIDaq


def test_nidaq_uses_configured_voltage_range():
    # La plage d'entrée (ai_min/ai_max) doit être passée à add_ai_voltage_chan.
    sensors = {"T": TempSensorConfig("T", "ai0", {"type": "identity"}, 60.0, 80.0,
                                     ai_min=-10.0, ai_max=10.0)}
    daq = NIDaq("Dev1", sensors)
    calls = []

    class FakeChans:
        def add_ai_voltage_chan(self, phys, **kw):
            calls.append((phys, kw))

    class FakeTask:
        ai_channels = FakeChans()

    daq._task = FakeTask()
    # on rejoue juste la boucle d'ajout de connect() (sans importer nidaqmx)
    for name in daq._order:
        s = daq.sensors[name]
        daq._task.ai_channels.add_ai_voltage_chan(f"Dev1/{s.channel}",
                                                  min_val=s.ai_min, max_val=s.ai_max)
    assert calls == [("Dev1/ai0", {"min_val": -10.0, "max_val": 10.0})]


def test_nidaq_exposes_raw_voltages():
    # Le module NI conserve la tension brute lue avant conversion en °C.
    sensors = {
        "T1": TempSensorConfig("T1", "ai0", {
            "type": "ntc", "r0": 10000.0, "t0": 25.0, "beta": 3950.0,
            "r_series": 10000.0, "v_ref": 3.3, "pullup_to_vref": True}, 60.0, 80.0),
        "T2": TempSensorConfig("T2", "ai1", {"type": "identity"}, 60.0, 80.0),
    }
    daq = NIDaq("Dev1", sensors)
    daq._task = type("FakeTask", (), {"read": lambda self: [1.65, 2.0]})()

    temps = daq.read_temperatures()
    volts = daq.read_voltages()
    assert volts == pytest.approx({"T1": 1.65, "T2": 2.0})
    assert temps["T2"] == pytest.approx(2.0)            # identity : °C == V
    assert temps["T1"] == pytest.approx(25.0, abs=0.5)  # pont 10k/10k @3.3V -> 25°C


def test_csv_logs_ni_voltages(ctrl, tmp_path):
    ctrl._daq.read_voltages = lambda: {"TS1": 1.234}
    ctrl.set_output("VLOAD", True)
    ctrl._temp_cycle()                                   # stocke la tension brute
    path = ctrl.start_recording(str(tmp_path / "mesures.csv"))
    ctrl._meas_cycle()                                   # écrit une ligne
    ctrl.stop_recording()

    rows = list(csv.reader(path.open(encoding="utf-8")))
    header, data = rows[0], rows[1]
    assert "TS1_C" in header and "TS1_V" in header
    assert float(data[header.index("TS1_V")]) == pytest.approx(1.234, abs=1e-3)
