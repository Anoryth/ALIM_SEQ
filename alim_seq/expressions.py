"""Évaluateur d'expressions arithmétiques sûr pour les consignes calculées.

Permet d'écrire dans une séquence des consignes dépendant d'autres voies, p. ex.

    SETV VG2 = (VD/2) + VG1

Un **nom de voie nu** (ex. ``VG1``, ``VD``) vaut sa **consigne de tension**
courante — utile pour récupérer une valeur trouvée par un ``SERVO`` précédent,
ou la tension totale d'un groupe série. Des fonctions donnent accès aux autres
grandeurs :

    V(x) / Vset(x) : consigne de tension de x   (= x tout court)
    Vmeas(x)       : tension MESURÉE de x
    Iset(x)        : limite de courant (consigne) de x
    I(x) / Imeas(x): courant MESURÉ de x

Opérateurs autorisés : ``+ - * /``, parenthèses, signe unaire, nombres. Aucun
autre nom/appel n'est accepté (sécurité : on n'évalue jamais de code arbitraire).
"""

from __future__ import annotations

import ast
import operator
from typing import Callable, Set, Tuple

# kind transmis au résolveur pour chaque référence.
_FUNCS = {
    "v": "V", "vset": "V",
    "vmeas": "Vmeas", "vm": "Vmeas",
    "iset": "Iset",
    "i": "Imeas", "imeas": "Imeas",
}

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

# Résolveur : (kind, label) -> valeur. kind ∈ {"V","Vmeas","Iset","Imeas"}.
Resolver = Callable[[str, str], float]


class ExprError(Exception):
    """Erreur de syntaxe ou de référence dans une expression."""


def _parse(expr: str) -> ast.Expression:
    try:
        return ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"expression invalide : {expr!r} ({exc.msg})") from exc


def references(expr: str) -> Set[str]:
    """Retourne l'ensemble des labels de voies référencés par l'expression.

    Valide aussi la structure (nœuds autorisés, fonctions connues) et lève
    :class:`ExprError` sinon. Utilisé à l'analyse de la séquence pour vérifier
    que toutes les voies existent avant l'exécution.
    """
    tree = _parse(expr)
    labels: Set[str] = set()
    _walk_validate(tree.body, labels)
    return labels


def _walk_validate(node: ast.AST, labels: Set[str]) -> None:
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINOPS:
            raise ExprError(f"opérateur non autorisé : {type(node.op).__name__}")
        _walk_validate(node.left, labels)
        _walk_validate(node.right, labels)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARYOPS:
            raise ExprError(f"opérateur unaire non autorisé : {type(node.op).__name__}")
        _walk_validate(node.operand, labels)
    elif isinstance(node, ast.Name):
        labels.add(node.id)
    elif isinstance(node, ast.Call):
        _, label = _check_call(node)
        labels.add(label)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            raise ExprError(f"constante non numérique : {node.value!r}")
    else:
        raise ExprError(f"élément non autorisé dans l'expression : {type(node).__name__}")


def _check_call(node: ast.Call) -> Tuple[str, str]:
    """Valide un appel fonction(label) et retourne (kind, label)."""
    if not isinstance(node.func, ast.Name):
        raise ExprError("appel de fonction invalide")
    fname = node.func.id.lower()
    if fname not in _FUNCS:
        raise ExprError(
            f"fonction inconnue : {node.func.id!r}. "
            f"Disponibles : V, Vmeas, Iset, I"
        )
    if len(node.args) != 1 or node.keywords or not isinstance(node.args[0], ast.Name):
        raise ExprError(f"{node.func.id}(...) attend un seul nom de voie")
    return _FUNCS[fname], node.args[0].id


def evaluate(expr: str, resolver: Resolver) -> float:
    """Évalue l'expression. Un nom nu = consigne de tension (kind 'V')."""
    tree = _parse(expr)
    return _eval(tree.body, resolver)


def _eval(node: ast.AST, resolver: Resolver) -> float:
    if isinstance(node, ast.BinOp):
        return _BINOPS[type(node.op)](_eval(node.left, resolver), _eval(node.right, resolver))
    if isinstance(node, ast.UnaryOp):
        return _UNARYOPS[type(node.op)](_eval(node.operand, resolver))
    if isinstance(node, ast.Name):
        return float(resolver("V", node.id))
    if isinstance(node, ast.Call):
        kind, label = _check_call(node)
        return float(resolver(kind, label))
    if isinstance(node, ast.Constant):
        return float(node.value)
    raise ExprError(f"élément non autorisé : {type(node).__name__}")
