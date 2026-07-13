"""Tests de l'évaluateur d'expressions (consignes calculées SETV/SETI)."""

import pytest

from alim_seq.expressions import ExprError, evaluate, references


def _resolver(values):
    def get(kind, label):
        return values[kind][label]
    return get


def test_basic_arithmetic_with_signed_values():
    vals = {"V": {"VD": 30.0, "VG1": -2.0}}
    get = _resolver(vals)
    assert evaluate("(VD/2)+VG1", get) == pytest.approx(13.0)   # 15 + (-2)
    assert evaluate("(VD/2)-VG1", get) == pytest.approx(17.0)   # 15 - (-2)
    assert evaluate("VG1*2", get) == pytest.approx(-4.0)


def test_functions():
    vals = {"V": {"X": 1.0}, "Vmeas": {"X": 1.5}, "Iset": {"X": 0.2}, "Imeas": {"X": 0.3}}
    get = _resolver(vals)
    assert evaluate("Vmeas(X)", get) == 1.5
    assert evaluate("Iset(X)*10", get) == pytest.approx(2.0)
    assert evaluate("I(X)", get) == 0.3


def test_references_collects_labels():
    assert references("(VD/2)+VG1") == {"VD", "VG1"}
    assert references("Vmeas(A)+V(B)") == {"A", "B"}


@pytest.mark.parametrize("expr", [
    "__import__('os')",
    "VD**2",
    "foo(VD)",
    "VD; VG1",
    "VD.real",
])
def test_unsafe_expressions_rejected(expr):
    with pytest.raises(ExprError):
        references(expr)
