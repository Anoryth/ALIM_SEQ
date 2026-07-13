"""Thème de l'IHM Qt : autorité unique des couleurs via des **jetons sémantiques**.

Chaque jeton porte une valeur ``(bg, fg)`` par thème (clair / sombre). Les helpers
:func:`pair` et :func:`style` lisent le thème courant du module (mis à jour par
:func:`apply_theme`), de sorte qu'un style émis via :func:`style` est TOUJOURS
lisible dans le thème actif : on émet toujours ``background-color`` ET ``color``
ensemble quand le jeton a un fond, jamais l'un sans l'autre. C'est la règle qui
corrige le bug racine (fond fixé, texte hérité → illisible dans l'autre thème).

RÈGLE (piège Qt) : **un stylesheet gèle la résolution de palette du widget**. Un
widget portant le moindre ``setStyleSheet`` — même purement typographique (``font-*``,
``padding``…) — est rendu par ``QStyleSheetStyle`` et n'est plus repeint par un
``QApplication.setPalette()`` ultérieur : il garde la couleur de texte résolue à sa
construction (donc devient illisible après un changement de thème). En conséquence :
- toute propriété **typographique** (gras, taille…) passe par ``QFont``
  (``f = w.font(); f.setBold(True); w.setFont(f)``), jamais par un stylesheet ;
- toute **couleur** passe par :func:`style`, qui émet fond ET texte ensemble.
``tests/test_theme.py`` interdit statiquement tout littéral de stylesheet sans
``color:`` (fond sans texte, ou typo sans couleur)."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..controller import CRITICAL, FAULT, NA, OK, WARNING

# Jeton -> ((bg_clair, fg_clair), (bg_sombre, fg_sombre)).
#   - jetons à fond : contraste texte/fond ≥ 4.5:1 dans les DEUX thèmes
#     (vérifié par tests/test_theme.py) ; fond saturé sombre + texte clair en sombre.
#   - jetons ``text.*`` : fg seul (bg = None), choisis pour rester lisibles sur les
#     deux fonds ambiants.
#   - jetons à valeurs FIXES (boutons d'action, badges, ligne en cours, syntaxe) :
#     mêmes couleurs dans les deux thèmes (elles fixent déjà fond ET texte, ou sont
#     de luminance moyenne pour la syntaxe).
_TOKENS = {
    # Statuts de sécurité / niveaux (fond + texte).
    "status.ok":        (("#e8f5e9", "#1b5e20"), ("#1b3a22", "#a5d6a7")),
    "status.warning":   (("#fff8e1", "#7a5c00"), ("#4a3a00", "#ffd54f")),
    "status.critical":  (("#ffebee", "#b71c1c"), ("#4a1414", "#ef9a9a")),
    "status.na":        (("#f5f5f5", "#616161"), ("#3a3a3a", "#bdbdbd")),
    "status.fault":     (("#f3e5f5", "#6a1b9a"), ("#3d1b45", "#ce93d8")),
    # Consigne modifiée non appliquée (fond + texte).
    "pending":          (("#fff3bf", "#4e3c00"), ("#4a3f12", "#ffe082")),
    # Textes sans fond (lisibles sur clair et sombre).
    "text.muted":       ((None, "#616161"), (None, "#aaaaaa")),
    "text.ok":          ((None, "#2e7d32"), (None, "#81c784")),
    "text.error":       ((None, "#c62828"), (None, "#ef9a9a")),
    "text.info":        ((None, "#1565c0"), (None, "#64b5f6")),
    # Boutons/badges à couleurs fixes (fond + texte, identiques dans les deux thèmes).
    "button.emergency": (("#c62828", "#ffffff"), ("#c62828", "#ffffff")),
    "button.shutdown":  (("#ef6c00", "#ffffff"), ("#ef6c00", "#ffffff")),
    "button.start":     (("#2e7d32", "#ffffff"), ("#2e7d32", "#ffffff")),
    "button.apply":     (("#1565c0", "#ffffff"), ("#1565c0", "#ffffff")),
    "button.on":        (("#2e7d32", "#ffffff"), ("#2e7d32", "#ffffff")),
    "button.off":       (("#cfd8dc", "#000000"), ("#cfd8dc", "#000000")),
    # Bouton secondaire de la barre de sécurité au repos (Réarmer, Tout OFF) — bithème,
    # dans la famille de button.off ; passe par QSS pour des métriques homogènes.
    "button.neutral":   (("#cfd8dc", "#1a1a1a"), ("#455a64", "#eceff1")),
    # Réarmer saillant après un déclenchement (orange gras, ex-button.shutdown).
    "button.rearm_alert": (("#ef6c00", "#ffffff"), ("#ef6c00", "#ffffff")),
    "badge.sim":        (("#1565c0", "#ffffff"), ("#1565c0", "#ffffff")),
    "badge.real":       (("#bf360c", "#ffffff"), ("#bf360c", "#ffffff")),
    "editor.runline":   (("#2e7d32", "#ffffff"), ("#2e7d32", "#ffffff")),
    # Coloration syntaxique de l'éditeur (fg seul, luminance moyenne : les mêmes
    # valeurs passent en clair et en sombre — voir SeqHighlighter).
    "syntax.command":   ((None, "#2196f3"), (None, "#2196f3")),
    "syntax.comment":   ((None, "#9e9e9e"), (None, "#9e9e9e")),
    "syntax.number":    ((None, "#fb8c00"), (None, "#fb8c00")),
    "syntax.key":       ((None, "#ab47bc"), (None, "#ab47bc")),
    "syntax.label":     ((None, "#43a047"), (None, "#43a047")),
    "syntax.op":        ((None, "#ec407a"), (None, "#ec407a")),
    # Tracé du mini-graphe tension→°C (fg seul, thème-aware).
    "plot.curve":       ((None, "#1565c0"), (None, "#64b5f6")),
    "plot.marker":      ((None, "#e53935"), (None, "#ef5350")),
}

# Niveau de sécurité -> jeton de statut (remplace les anciens dicts de niveau).
_LEVEL_TOKENS = {
    OK: "status.ok", WARNING: "status.warning", CRITICAL: "status.critical",
    NA: "status.na", FAULT: "status.fault",
}

# État de thème courant du module (tenu à jour par apply_theme).
_dark = False


def set_dark(dark: bool) -> None:
    """Fixe l'état de thème courant du module (clair/sombre)."""
    global _dark
    _dark = bool(dark)


def is_dark() -> bool:
    return _dark


def level_token(level: str) -> str:
    """Jeton ``status.*`` correspondant à un niveau OK/WARNING/CRITICAL/NA/FAULT."""
    return _LEVEL_TOKENS.get(level, "status.na")


def pair(token: str):
    """(bg, fg) du jeton dans le thème courant. ``bg`` peut être None (jeton texte)."""
    return _TOKENS[token][1 if _dark else 0]


def style(token: str, extra: str = "", fg_only: bool = False) -> str:
    """Stylesheet complet pour le jeton dans le thème courant.

    Si le jeton a un fond, émet TOUJOURS ``background-color`` ET ``color`` ensemble ;
    sinon ``color`` seul. ``fg_only=True`` force la couleur de texte seule (utile
    pour appliquer la teinte d'un jeton à fond sur un simple label, sans le remplir).
    ``extra`` (ex. ``"padding:6px;"``) est ajouté tel quel."""
    bg, fg = pair(token)
    css = "" if (bg is None or fg_only) else f"background-color:{bg}; "
    css += f"color:{fg};"
    if extra:
        css += " " + extra
    return css


def dark_palette() -> QtGui.QPalette:
    p = QtGui.QPalette()
    dark, base, text = QtGui.QColor(53, 53, 53), QtGui.QColor(35, 35, 35), QtCore.Qt.white
    p.setColor(QtGui.QPalette.Window, dark)
    p.setColor(QtGui.QPalette.WindowText, text)
    p.setColor(QtGui.QPalette.Base, base)
    p.setColor(QtGui.QPalette.AlternateBase, dark)
    p.setColor(QtGui.QPalette.ToolTipBase, dark)
    p.setColor(QtGui.QPalette.ToolTipText, text)
    p.setColor(QtGui.QPalette.Text, text)
    p.setColor(QtGui.QPalette.Button, dark)
    p.setColor(QtGui.QPalette.ButtonText, text)
    p.setColor(QtGui.QPalette.Link, QtGui.QColor(42, 130, 218))
    p.setColor(QtGui.QPalette.Highlight, QtGui.QColor(42, 130, 218))
    p.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.black)
    # Texte indicatif (placeholder) : sans cette couleur, il reste sombre → invisible
    # sur le fond sombre (ex. le champ « Rechercher dans le journal… »).
    p.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor(150, 150, 150))
    for role in (QtGui.QPalette.Text, QtGui.QPalette.ButtonText, QtGui.QPalette.WindowText):
        p.setColor(QtGui.QPalette.Disabled, role, QtGui.QColor(127, 127, 127))
    return p


def apply_theme(dark: bool) -> None:
    """Pose la palette (claire/sombre) ET met à jour l'état de thème du module,
    de sorte que tout appel ultérieur à :func:`style`/:func:`pair` reflète le thème."""
    set_dark(dark)
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    app.setPalette(dark_palette() if dark else app.style().standardPalette())
