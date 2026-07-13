"""Exécution d'opérations matérielles bloquantes (VISA/NI) hors du thread GUI.

Un timeout VISA de plusieurs secondes exécuté dans le thread Qt fige toute la
fenêtre (bannière et bouton d'urgence compris). :class:`Task` déporte un callable
dans un QThread et rapporte le résultat par signaux — qui traversent les threads
proprement. La fonction exécutée ne DOIT jamais toucher un widget."""

from __future__ import annotations

from typing import Callable

from PySide6 import QtCore


class Task(QtCore.QThread):
    """Exécute ``fn()`` dans un thread dédié et émet ``done(résultat)`` ou
    ``failed(message)``. Aucun accès widget dans ``fn`` : seuls les signaux
    (reçus dans le thread GUI) mettent l'IHM à jour."""

    done = QtCore.Signal(object)     # résultat de fn()
    failed = QtCore.Signal(str)      # message d'erreur

    def __init__(self, fn: Callable[[], object], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:   # exécuté dans le thread secondaire
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - on rapporte tout à l'IHM
            self.failed.emit(str(exc))
            return
        self.done.emit(result)
