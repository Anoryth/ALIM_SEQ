"""Drivers d'actionneurs (relais / commutateurs) — capacité ``Actionneur``.

Un relais expose des **sorties nommées** (labels) que l'on ouvre/ferme
individuellement. C'est la première capacité *neuve* posée sur l'abstraction par
capacités (cf. docs/DESIGN_INSTRUMENTS.md, ROADMAP §4) : elle s'ajoute sans toucher
au cœur du contrôleur.

- :class:`BaseRelay`  : interface commune (sorties par label).
- :class:`MockRelay`  : relais simulé (état en mémoire). Sert la parité simulation
                        et fait aussi office de **relais « virtuel »** pilotable à la
                        main quand aucun matériel n'est câblé.

Aucun modèle matériel réel n'est encore intégré : quand un modèle sera choisi, son
driver se sous-classera de :class:`BaseRelay` et s'enregistrera dans le registre
unifié ``alim_seq.instrument.INSTRUMENTS`` — exactement comme un modèle d'alim.

Le relais NE fait PAS de verrouillage : la sérialisation des accès est gérée par le
contrôleur (un verrou par instrument).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .instrument import Actionneur, Instrument


class BaseRelay(Instrument, Actionneur):
    """Interface d'un relais multi-sorties adressées par **label**.

    ``outputs`` est la liste ordonnée des labels de sortie exposés. L'état d'une
    sortie est booléen : ``True`` = fermé/activé (ON), ``False`` = ouvert/repos (OFF).
    """

    def __init__(self, name: str = "RELAY", outputs: Optional[List[str]] = None):
        self.name = name
        self.model = "BaseRelay"
        self.outputs: List[str] = list(outputs or [])

    def connect(self) -> None: ...
    def close(self) -> None: ...

    def set_state(self, label: str, on: bool) -> None: ...
    def get_state(self, label: str) -> Optional[bool]: ...

    def states(self) -> Dict[str, bool]:
        """État courant de toutes les sorties (``{label: bool}``)."""
        return {lbl: bool(self.get_state(lbl)) for lbl in self.outputs}

    def all_off(self) -> None:
        """Ouvre (met à OFF) toutes les sorties."""
        for lbl in self.outputs:
            self.set_state(lbl, False)


class MockRelay(BaseRelay):
    """Relais simulé : l'état des sorties est tenu en mémoire (aucune I/O)."""

    def __init__(self, name: str = "RELAY", outputs: Optional[List[str]] = None):
        super().__init__(name=name, outputs=outputs)
        self.model = "MockRelay"
        self._state: Dict[str, bool] = {lbl: False for lbl in self.outputs}

    def connect(self) -> None:
        pass

    def close(self) -> None:
        # À la fermeture on ouvre tout (état de repos sûr par défaut).
        self.all_off()

    def set_state(self, label: str, on: bool) -> None:
        if label not in self._state:
            raise KeyError(f"Sortie de relais inconnue : {label!r}")
        self._state[label] = bool(on)

    def get_state(self, label: str) -> Optional[bool]:
        return self._state.get(label)
