"""CSV recording and test folder — :class:`Controller` mixin.

Extracted from ``controller.py`` (god-object decomposition): this mixin groups the
upkeep of the ``mesures.csv`` file and the self-contained test folder. It **shares
the controller's state** (``self._rec_lock``, ``self._csv_*``, ``self._essai``,
``self.cfg``, ``self._state_lock``/``self._set``, ``self.runner``, ``self.log``…) —
this is a pure code move, no behavior change. ``_record_row`` is still called by the
core's measurement loop.
"""

from __future__ import annotations

import csv
import time
from datetime import datetime

from .i18n import _
from pathlib import Path
from typing import Dict, Optional, Tuple

from .essai import (DossierEssai, ISSUE_ARRET_UTILISATEUR, ISSUE_TERMINE)


class RecordingMixin:
    """Measurement recording (CSV) + test folder. Grafted onto ``Controller``."""

    # ----------------------------------------------------- CSV recording
    def start_recording(self, path: Optional[str] = None, nom: str = "",
                        operateur: str = "") -> Path:
        """Starts recording the measurements and returns the CSV path.

        Without an explicit ``path``, creates a **self-contained test folder**
        (``logs/essais/…``) and writes ``mesures.csv`` into it: the configuration,
        the sequence, the log and the metadata are archived alongside. ``nom`` and
        ``operateur`` (optional) name the test. An explicit ``path`` writes a raw
        CSV with no folder (useful for tests and one-off exports)."""
        with self._rec_lock:
            if self._csv_writer is not None:
                return self._csv_path  # already in progress
            if path is None:
                self._essai = DossierEssai(self, nom=nom, operateur=operateur)
                path = self._essai.mesures_path
            self._csv_path = Path(path)
            self._csv_file = self._csv_path.open("w", newline="", encoding="utf-8")
            header = ["horodatage", "t_s"]
            for name in self.cfg.temperatures:
                # Converted °C + raw NI voltage (V) side by side, as a safety net.
                header += [f"{name}_C", f"{name}_V"]
            for label in self.cfg.channels:
                header += [f"{label}_Vset", f"{label}_Iset",
                          f"{label}_Vmeas", f"{label}_Imeas", f"{label}_out"]
            header.append("securite")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow(header)
            self._csv_t0 = time.monotonic()
        self.log(_("Recording started: {}").format(self._csv_path))
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
            essai.finalize()   # freezes the end timestamp + the outcome in essai.json
        if self._csv_path:
            self.log(_("Recording stopped: {}").format(self._csv_path))

    @property
    def is_recording(self) -> bool:
        return self._csv_writer is not None

    @property
    def essai(self) -> Optional[DossierEssai]:
        """Current test folder (None outside a recording or in raw-CSV mode)."""
        return self._essai

    @property
    def recording_dossier(self) -> Optional[str]:
        """Name of the current test folder, for the GUI display (None otherwise)."""
        e = self._essai
        return e.path.name if e is not None else None

    def _runner_finished(self, ok: bool, msg: str) -> None:
        """Intercepts the end of a sequence: updates the test outcome (except for a
        safety power-down, which is not the test's outcome) then relays it to the
        GUI."""
        essai = self._essai
        if essai is not None and not self.runner._safety_mode:
            essai.set_issue(ISSUE_TERMINE if ok else ISSUE_ARRET_UTILISATEUR)
        if self.on_seq_finish is not None:
            self.on_seq_finish(ok, msg)

    def _record_row(self, meas: Dict[str, Tuple[float, float]],
                    temps: Dict[str, float], volts: Dict[str, float],
                    status: str) -> None:
        # Consistent snapshot of the setpoints UNDER _state_lock (they are mutated
        # by other threads) before composing the CSV row.
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
