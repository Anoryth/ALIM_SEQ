#!/usr/bin/env python3
"""Point d'entrée du séquenceur d'alimentation.

Usage :
    python main.py [--config config.json]

L'interface graphique est **Qt (PySide6)**. Le mode (simulation ou matériel réel)
est déterminé par le champ "simulate" du fichier de configuration.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alim_seq.config import load_config
from alim_seq.controller import Controller

# Dossier du projet (là où se trouve ce script).
PROJECT_DIR = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Séquenceur d'alimentation HMP4040 / NI")
    parser.add_argument(
        "--config", default="config.json", help="Fichier de configuration (défaut: config.json)"
    )
    args = parser.parse_args()

    # Résout le fichier de config AVANT de changer de répertoire (un chemin
    # relatif donné par l'utilisateur reste relatif à son répertoire courant).
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute() and not cfg_path.exists():
        # Repli : cherche à côté du script (rend le dossier autoporteur).
        candidate = PROJECT_DIR / args.config
        if candidate.exists():
            cfg_path = candidate
    cfg_path = cfg_path.resolve() if cfg_path.exists() else cfg_path

    # Se rattache au dossier du projet pour que sequences/ et logs/ soient
    # toujours résolus correctement, quel que soit le répertoire de lancement.
    # En mode empaqueté (PyInstaller), le lanceur a déjà placé le cwd dans un
    # dossier de données inscriptible — on n'écrase donc pas ce choix.
    if not getattr(sys, "frozen", False):
        os.chdir(PROJECT_DIR)

    if not cfg_path.exists():
        print(f"Configuration introuvable : {cfg_path}", file=sys.stderr)
        return 2

    try:
        cfg = load_config(cfg_path)
    except ValueError as exc:
        print(f"Erreur de configuration :\n{exc}", file=sys.stderr)
        return 2

    ctrl = Controller(cfg)
    ctrl.enable_file_logging()  # journal applicatif -> logs/alim_seq.log

    try:
        from alim_seq.gui_qt import run as run_qt
    except ImportError as exc:
        print("PySide6 est requis pour l'interface graphique d'ALIM_SEQ.\n"
              "  Installer les dépendances de l'IHM :  pip install -r requirements-qt.txt\n"
              f"  (détail : {exc})", file=sys.stderr)
        return 2
    run_qt(ctrl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
