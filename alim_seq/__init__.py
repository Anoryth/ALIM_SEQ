"""Séquenceur d'alimentation pour banc de test (HMP4040 + acquisition NI).

Modules principaux :
    config       : chargement et validation de la configuration JSON
    temperature  : convertisseurs tension -> température (non linéaires)
    instrument   : abstraction des appareils par capacités + registre unifié
    psu          : drivers alimentations (HMP4040 réel + mock)
    daq          : drivers acquisition NI (réel + mock thermique)
    relay        : drivers d'actionneurs / relais (capacité Actionneur, mock)
    safety       : surveillance température et arrêt d'urgence
    sequencer    : analyse et exécution d'un fichier de séquence (+ asservissement)
    controller   : orchestration, boucle de mesure, état partagé thread-safe
    gui_qt       : interface graphique Qt (PySide6), l'unique IHM
"""

# Version : générée au build depuis le tag git (alim_seq/_version.py, non versionné,
# écrit par la CI). Repli pour une exécution depuis les sources sans tag.
try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0-dev"
