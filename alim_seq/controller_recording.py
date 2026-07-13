"""Enregistrement CSV et dossier d'essai — mixin du :class:`Controller`.

Extrait de ``controller.py`` (décomposition de l'objet-dieu) : ce mixin regroupe la
tenue du fichier ``mesures.csv`` et du dossier d'essai autonome. Il **partage l'état**
du contrôleur (``self._rec_lock``, ``self._csv_*``, ``self._essai``, ``self.cfg``,
``self._state_lock``/``self._set``, ``self.runner``, ``self.log``…) — c'est du pur
déplacement de code, sans changement de comportement. ``_record_row`` reste appelé par
la boucle de mesure du cœur.
"""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from .essai import (DossierEssai, ISSUE_ARRET_UTILISATEUR, ISSUE_TERMINE)


class RecordingMixin:
    """Enregistrement des mesures (CSV) + dossier d'essai. Greffé sur ``Controller``."""

    # ----------------------------------------------------- enregistrement CSV
    def start_recording(self, path: Optional[str] = None, nom: str = "",
                        operateur: str = "") -> Path:
        """Démarre l'enregistrement des mesures et retourne le chemin du CSV.

        Sans ``path`` explicite, crée un **dossier d'essai autonome**
        (``logs/essais/…``) et y écrit ``mesures.csv`` : la configuration, la
        séquence, le journal et les métadonnées sont archivés à côté. ``nom`` et
        ``operateur`` (facultatifs) nomment l'essai. Un ``path`` explicite écrit
        un CSV brut sans dossier (utile aux tests et exports ponctuels)."""
        with self._rec_lock:
            if self._csv_writer is not None:
                return self._csv_path  # déjà en cours
            if path is None:
                self._essai = DossierEssai(self, nom=nom, operateur=operateur)
                path = self._essai.mesures_path
            self._csv_path = Path(path)
            self._csv_file = self._csv_path.open("w", newline="", encoding="utf-8")
            header = ["horodatage", "t_s"]
            for name in self.cfg.temperatures:
                # °C converti + tension NI brute (V) en regard, comme filet de sécurité.
                header += [f"{name}_C", f"{name}_V"]
            for label in self.cfg.channels:
                header += [f"{label}_Vset", f"{label}_Iset",
                          f"{label}_Vmeas", f"{label}_Imeas", f"{label}_out"]
            header.append("securite")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow(header)
            self._csv_t0 = time.monotonic()
        self.log(f"Enregistrement démarré : {self._csv_path}")
        return self._csv_path

    def stop_recording(self) -> None:
        with self._rec_lock:
            if self._csv_file is not None:
                self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
            essai = self._essai
            self._essai = None
        if essai is not None:
            essai.finalize()   # fige l'horodatage de fin + l'issue dans essai.json
        if self._csv_path:
            self.log(f"Enregistrement arrêté : {self._csv_path}")

    @property
    def is_recording(self) -> bool:
        return self._csv_writer is not None

    @property
    def essai(self) -> Optional[DossierEssai]:
        """Dossier d'essai en cours (None hors enregistrement ou en CSV brut)."""
        return self._essai

    @property
    def recording_dossier(self) -> Optional[str]:
        """Nom du dossier d'essai en cours, pour l'affichage IHM (None sinon)."""
        e = self._essai
        return e.path.name if e is not None else None

    def _runner_finished(self, ok: bool, msg: str) -> None:
        """Intercepte la fin de séquence : met à jour l'issue de l'essai (hors
        désalimentation de sécurité, qui n'est pas l'issue de l'essai) puis relaie
        à l'IHM."""
        essai = self._essai
        if essai is not None and not self.runner._safety_mode:
            essai.set_issue(ISSUE_TERMINE if ok else ISSUE_ARRET_UTILISATEUR)
        if self.on_seq_finish is not None:
            self.on_seq_finish(ok, msg)

    def _record_row(self, meas: Dict[str, Tuple[float, float]],
                    temps: Dict[str, float], volts: Dict[str, float],
                    status: str) -> None:
        # Instantané cohérent des consignes SOUS _state_lock (elles sont mutées par
        # d'autres threads) avant de composer la ligne CSV.
        with self._state_lock:
            sp = {label: (self._set[label].set_voltage, self._set[label].set_current,
                          self._set[label].output)
                  for label in self.cfg.channels}
        with self._rec_lock:
            if self._csv_writer is None:
                return
            row = [datetime.now().isoformat(timespec="milliseconds"),
                   f"{time.monotonic() - self._csv_t0:.3f}"]
            for name in self.cfg.temperatures:
                row += [f"{temps.get(name, float('nan')):.3f}",
                        f"{volts.get(name, float('nan')):.4f}"]
            for label in self.cfg.channels:
                set_v, set_i, out = sp[label]
                v, i = meas.get(label, (0.0, 0.0))
                row += [f"{set_v:.3f}", f"{set_i:.3f}",
                        f"{v:.4f}", f"{i:.4f}", "1" if out else "0"]
            row.append(status)
            self._csv_writer.writerow(row)
            self._csv_file.flush()
