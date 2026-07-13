"""Tests des convertisseurs tension -> température."""

import math

import pytest

from alim_seq.temperature import build_converter, parse_table_csv


def test_thermocouple_k_and_cjc():
    k = build_converter({"type": "thermocouple", "tc_type": "K", "cjc_c": 0})
    assert k.to_celsius(0.004096) == pytest.approx(100.0, abs=1.5)   # 4.096 mV ~ 100°C
    k25 = build_converter({"type": "tc", "tc_type": "K", "cjc_c": 25})
    assert k25.to_celsius(0.0) == pytest.approx(25.0, abs=2.0)        # soudure froide


def test_thermocouple_type_j_and_unknown():
    j = build_converter({"type": "thermocouple", "tc_type": "J", "cjc_c": 0})
    assert j.to_celsius(0.005269) == pytest.approx(100.0, abs=2.0)
    with pytest.raises(ValueError):
        build_converter({"type": "thermocouple", "tc_type": "Z"})


def test_parse_table_csv_separators():
    pts = parse_table_csv("# tension,°C\n0.2,100\n1.6;25\n3.0 -20\n")
    assert pts == [[0.2, 100.0], [1.6, 25.0], [3.0, -20.0]]
    with pytest.raises(ValueError):
        parse_table_csv("seulement une ligne\n")


def test_ntc_at_r0_gives_t0():
    conv = build_converter({"type": "ntc", "r_series": 10000, "v_ref": 3.3,
                            "r0": 10000, "t0": 25, "beta": 3950, "pullup_to_vref": True})
    # À mi-tension (v_ref/2) le pont donne R = r_series = r0 -> T = t0.
    assert conv.to_celsius(3.3 / 2) == pytest.approx(25.0, abs=0.1)


def test_ntc_monotonic():
    conv = build_converter({"type": "ntc", "r_series": 10000, "v_ref": 3.3,
                            "r0": 10000, "t0": 25, "beta": 3950, "pullup_to_vref": True})
    # Câblage pullup_to_vref : tension haute -> R_ntc haute -> NTC plus froide.
    assert conv.to_celsius(2.5) < conv.to_celsius(1.65) < conv.to_celsius(1.0)


def test_table_interpolation_and_bounds():
    conv = build_converter({"type": "table", "points": [[0.2, 100.0], [1.6, 25.0], [3.0, -20.0]]})
    assert conv.to_celsius(1.6) == pytest.approx(25.0)
    # Interpolation à mi-segment.
    assert conv.to_celsius(0.9) == pytest.approx(100.0 + (25.0 - 100.0) * (0.9 - 0.2) / (1.6 - 0.2))
    # Extrapolation hors bornes (monotone).
    assert conv.to_celsius(0.0) > 100.0
    assert conv.to_celsius(4.0) < -20.0


def test_ptc_linear_and_monotonic():
    # PT1000 (r0=1000 @ 0°C, alpha=0.00385) sur pont 1k vers 3.3V, PTC vers GND.
    conv = build_converter({"type": "ptc", "r_series": 1000, "v_ref": 3.3,
                            "r0": 1000, "t0": 0, "alpha": 0.00385,
                            "pullup_to_vref": True})
    # À 0°C, R=R0 -> point milieu = v_ref/2 = 1.65 V.
    assert conv.to_celsius(1.65) == pytest.approx(0.0, abs=0.2)
    # PTC : la tension MONTE quand la température monte (R augmente).
    assert conv.to_celsius(2.0) > conv.to_celsius(1.65)


def test_rtd_alias():
    a = build_converter({"type": "ptc", "r_series": 1000, "v_ref": 3.3,
                         "r0": 1000, "t0": 0, "alpha": 0.00385})
    b = build_converter({"type": "rtd", "r_series": 1000, "v_ref": 3.3,
                         "r0": 1000, "t0": 0, "alpha": 0.00385})
    assert a.to_celsius(2.0) == pytest.approx(b.to_celsius(2.0))


def test_polynomial():
    conv = build_converter({"type": "poly", "coeffs": [10.0, 2.0, 0.5]})
    assert conv.to_celsius(2.0) == pytest.approx(10 + 2 * 2 + 0.5 * 4)


def test_identity():
    conv = build_converter({"type": "identity"})
    assert conv.to_celsius(42.0) == 42.0


def test_unknown_converter_raises():
    with pytest.raises(ValueError):
        build_converter({"type": "magic"})


# --- T5 : détection capteur débranché / court-circuit (fault_margin) --------
def test_ntc_disconnected_returns_nan():
    conv = build_converter({"type": "ntc", "r_series": 10000, "v_ref": 3.3,
                            "r0": 10000, "t0": 25, "beta": 3950})
    # Câble ouvert -> tension collée à un rail (0 ou v_ref) -> NaN (défaut), et
    # SURTOUT pas une valeur « très froide » plausible.
    assert math.isnan(conv.to_celsius(0.0))
    assert math.isnan(conv.to_celsius(3.3))
    assert math.isnan(conv.to_celsius(0.01))     # dans la marge de 2 %
    assert math.isnan(conv.to_celsius(3.29))
    # Une tension utile normale reste une température finie.
    assert math.isfinite(conv.to_celsius(1.65))


def test_ptc_disconnected_returns_nan():
    conv = build_converter({"type": "ptc", "r_series": 1000, "v_ref": 3.3,
                            "r0": 1000, "t0": 0, "alpha": 0.00385})
    assert math.isnan(conv.to_celsius(0.0))
    assert math.isnan(conv.to_celsius(3.3))
    assert math.isfinite(conv.to_celsius(1.65))


def test_fault_margin_zero_disables_detection():
    conv = build_converter({"type": "ntc", "r_series": 10000, "v_ref": 3.3,
                            "r0": 10000, "t0": 25, "beta": 3950, "fault_margin": 0})
    # Détection désactivée : les garde-fous numériques évitent NaN/inf.
    assert math.isfinite(conv.to_celsius(0.0))
