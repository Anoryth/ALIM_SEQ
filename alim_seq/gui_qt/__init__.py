"""Interface graphique PySide6 (Qt) — l'unique IHM de l'application.

Onglets **Contrôle** (voies, groupes série, températures, séquence, sécurité,
journal), **Configuration** interactive, **Éditeur de séquence** et **Graphe**
température, branchés sur le même :class:`Controller`.

Lancement : ``python main.py``  (nécessite PySide6 ; voir requirements-qt.txt).

Ce module a été éclaté en sous-package ; ``run`` et ``AlimSeqQtGUI`` restent
importables directement depuis ``alim_seq.gui_qt`` (compat historique).
"""

from __future__ import annotations

from .main_window import AlimSeqQtGUI, run

__all__ = ["AlimSeqQtGUI", "run"]
