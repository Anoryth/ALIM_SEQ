"""Garde-fou anti-régression du système de thème de l'IHM Qt (analyse statique,
sans Qt réel) :

1. aucun stylesheet écrit en dur dans ``gui_qt`` (hors ``theme.py``, l'autorité) ne
   déclare une propriété CSS (``background``, ``font``, ``padding``, ``margin``,
   ``border``) SANS ``color:`` — cela couvre les DEUX pièges de gel de palette :
   fond sans texte, et stylesheet purement typographique (un widget stylé n'est plus
   repeint par ``setPalette`` → texte figé, illisible après un changement de thème) ;
2. chaque jeton à fond de ``theme._TOKENS`` respecte un contraste WCAG ≥ 4.5:1 dans
   les DEUX thèmes (clair et sombre) ;
3. les anciens dicts ``_BG``/``_FG`` ont bien disparu du code.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_GUI_QT = Path(__file__).resolve().parents[1] / "alim_seq" / "gui_qt"
_THEME_PY = _GUI_QT / "theme.py"
# theme.py est l'autorité : c'est le SEUL endroit qui assemble background-color et
# color (dans des littéraux distincts) ; il est donc exclu du scan.
_SCANNED = sorted(p for p in _GUI_QT.glob("*.py") if p.name != "theme.py")


def _load_tokens() -> dict:
    """Extrait ``_TOKENS`` par analyse du SOURCE de theme.py (ast.literal_eval), sans
    importer le package IHM : le test reste collectable/passant sur une machine SANS
    PySide6 (l'import de alim_seq.gui_qt entraînerait PySide6 via __init__/main_window)."""
    tree = ast.parse(_THEME_PY.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_TOKENS"):
            return ast.literal_eval(node.value)
    raise AssertionError("_TOKENS introuvable dans theme.py")


_TOKENS = _load_tokens()

# Propriétés CSS qui, présentes dans un stylesheet, imposent aussi une couleur de
# texte (sinon le widget fige la résolution de palette : cf. docstring de theme.py).
_CSS_PROPS = ("background-color", "background", "font", "padding", "margin", "border")
# Vraie déclaration « color: » (exclut « background-color: » / « border-color: » où
# « color » est précédé d'un tiret).
_TEXT_COLOR_RE = re.compile(r"(?<![-\w])color\s*:")


def _stylesheet_literals(source: str):
    """(lineno, texte) de chaque littéral passé DIRECTEMENT à ``setStyleSheet(...)``.
    Les appels dynamiques (``theme.style(...)``) sont ignorés : theme.style garantit
    déjà la couleur ; les fragments qu'on lui passe (ex. ``"padding:6px;"``) ne sont
    donc pas des stylesheets autonomes. On ne juge que les stylesheets écrits en dur."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setStyleSheet" and node.args):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            yield arg.lineno, arg.value
        elif isinstance(arg, ast.JoinedStr):
            yield arg.lineno, (ast.get_source_segment(source, arg) or "")


def _declares_css(text: str) -> bool:
    return any(prop in text for prop in _CSS_PROPS)


def _sets_text_color(text: str) -> bool:
    return bool(_TEXT_COLOR_RE.search(text))


def test_no_stylesheet_without_text_color():
    offenders = []
    for path in _SCANNED:
        source = path.read_text(encoding="utf-8")
        for lineno, text in _stylesheet_literals(source):
            if _declares_css(text) and not _sets_text_color(text):
                offenders.append(f"{path.name}:{lineno} -> {text!r}")
    assert not offenders, (
        "Stylesheet(s) en dur déclarant une propriété CSS sans couleur de texte "
        "(gel de palette → illisible après bascule de thème) :\n" + "\n".join(offenders))


def _rel_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(bg: str, fg: str) -> float:
    l1, l2 = _rel_luminance(bg), _rel_luminance(fg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# Jetons à couleurs de marque FIXES (boutons d'action / badges / ligne en cours),
# conservés à l'identique (Tâche 1). Leurs libellés sont en gras (≥ 14 pt bold) :
# ils relèvent du « grand texte » WCAG, dont le seuil AA est 3:1 (et non 4.5:1).
_LARGE_TEXT_TOKENS = {
    "button.emergency", "button.shutdown", "button.start", "button.apply",
    "button.on", "button.off", "button.rearm_alert", "badge.sim", "badge.real",
    "editor.runline",
}


def test_token_contrast_wcag():
    weak = []
    for token, ((lbg, lfg), (dbg, dfg)) in _TOKENS.items():
        threshold = 3.0 if token in _LARGE_TEXT_TOKENS else 4.5
        for name, bg, fg in (("clair", lbg, lfg), ("sombre", dbg, dfg)):
            if bg is None:            # jetons texte : pas de fond à contraster
                continue
            ratio = _contrast(bg, fg)
            if ratio < threshold:
                weak.append(f"{token} ({name}) : {ratio:.2f} < {threshold}  ({fg} sur {bg})")
    assert not weak, "Contraste WCAG insuffisant :\n" + "\n".join(weak)


def test_no_legacy_level_dicts():
    """Les anciens dicts _BG/_FG (une seule moitié de paire) ne doivent plus exister."""
    pat = re.compile(r"\b_(BG|FG)\b")
    hits = []
    for path in _GUI_QT.glob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                hits.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not hits, "Références résiduelles à _BG/_FG :\n" + "\n".join(hits)


def test_style_helper_emits_both_when_background():
    """style() émet TOUJOURS background-color ET color pour un jeton à fond, et
    color seul pour un jeton texte. (Nécessite Qt : ignoré sans PySide6.)"""
    try:
        from alim_seq.gui_qt import theme
    except ImportError:
        pytest.skip("PySide6 indisponible — vérification runtime ignorée")
    theme.set_dark(False)
    ok = theme.style("status.ok")
    assert "background-color:" in ok and "color:" in ok
    muted = theme.style("text.muted")
    assert "background-color:" not in muted and "color:" in muted
    # fg_only : teinte d'un jeton à fond appliquée en texte seul.
    fault = theme.style("status.fault", fg_only=True)
    assert "background-color:" not in fault and "color:" in fault
