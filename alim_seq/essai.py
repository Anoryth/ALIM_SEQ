"""Self-contained test folder: one recording = one reusable folder.

Every recording start creates ``logs/essais/YYYYMMDD_HHMMSS[_<name>]/`` which
gathers EVERYTHING needed to regenerate a report much later, without the
application still open on the test:

- ``mesures.csv``  : the measurement CSV (written by the controller);
- ``config.json``  : byte-for-byte copy of the active configuration;
- ``sequence.seq`` : exact text of the executed sequence (absent for purely
  manual control);
- ``journal.log``  : controller events during the test;
- ``essai.json``   : metadata (version, mode, timestamps, hashes, outcome,
  safety events).

This module does NOT depend on Qt: it is testable on its own. The controller
delegates the upkeep of the folder to it over the course of the test.

Note: the ``essai.json`` field names and the ``ISSUE_*`` string values below are
a persisted on-disk schema (also read back by ``rapport.py``), NOT display text —
they are kept as-is so existing test folders remain readable.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import __version__

# Possible test outcomes, from least to most severe. The rank acts as an
# anti-downgrade guard: a more severe outcome cannot be overwritten by a less
# severe one (a safety trip stays recorded even if the power-down later
# "finishes" cleanly). These string values are a persisted schema — keep as-is.
ISSUE_EN_COURS = "en_cours"
ISSUE_TERMINE = "termine"
ISSUE_ARRET_UTILISATEUR = "arret_utilisateur"
ISSUE_DECLENCHEMENT = "declenchement_securite"
_ISSUE_RANK = {
    ISSUE_EN_COURS: 0,
    ISSUE_TERMINE: 1,
    ISSUE_ARRET_UTILISATEUR: 2,
    ISSUE_DECLENCHEMENT: 3,
}

_FORBIDDEN = set('/\\:*?"<>|')


def safe_folder_name(nom: str) -> str:
    """Sanitize a test name into a safe folder component: spaces -> ``_``,
    forbidden characters ``/\\:*?"<>|`` removed, control characters stripped.
    Returns "" if nothing usable remains."""
    out = []
    for ch in (nom or "").strip():
        if ch in _FORBIDDEN:
            continue
        if ch.isspace():
            out.append("_")
        elif ord(ch) < 32:
            continue
        else:
            out.append(ch)
    # Collapse repeated underscores, strip leading/trailing underscores and dots
    # (a folder should not start with a dot nor end with a space/dot).
    name = "".join(out).strip("_. ")
    while "__" in name:
        name = name.replace("__", "_")
    return name


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DossierEssai:
    """Maintains the folder of an ongoing test. Created by ``start_recording``
    and finalized by ``stop_recording`` (or ``close``) on the controller side."""

    def __init__(self, ctrl, nom: str = "", operateur: str = "",
                 base_dir="logs/essais"):
        self.ctrl = ctrl
        self.nom = nom or ""
        self.operateur = operateur or ""
        self.simulate = bool(getattr(ctrl.cfg, "simulate", False))

        stamp = datetime.now()
        self.started_at = stamp
        self.finished_at: Optional[datetime] = None
        safe = safe_folder_name(self.nom)
        folder = stamp.strftime("%Y%m%d_%H%M%S") + (f"_{safe}" if safe else "")
        # Collision guard: the timestamp is second-resolution — two tests started
        # within the same second (fast stop/start) would share the folder and the
        # second one would OVERWRITE mesures.csv. We suffix _2, _3…; mkdir(
        # exist_ok=False) makes the test-and-create atomic (no TOCTOU across
        # instances).
        base = Path(base_dir)
        path = base / folder
        n = 2
        while True:
            try:
                path.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                path = base / f"{folder}_{n}"
                n += 1
        self.path = path
        self.mesures_path = self.path / "mesures.csv"

        self.issue = ISSUE_EN_COURS
        self.cause = ""
        self.conclusion = ""
        self._safety_events: List[dict] = []
        self._config_source: Optional[str] = None
        self._config_sha = ""
        self._sequence_sha = ""
        self._has_sequence = False

        self._lock = threading.Lock()
        self._journal = (self.path / "journal.log").open("a", encoding="utf-8")

        self._archive_config()
        # Subscribe to the controller log for the duration of the test.
        self.ctrl.add_log_listener(self._on_log)
        # Write a first version of essai.json (outcome = en_cours): the folder is
        # already usable even if the application is killed mid-test.
        self._write_metadata()

    # ------------------------------------------------------------- archiving
    def _archive_config(self) -> None:
        """Copy the active configuration into ``config.json`` and compute its
        hash. Byte-for-byte copy if the config came from a file (``source_path``),
        otherwise serialize the in-memory state."""
        from .config import config_to_dict

        cfg = self.ctrl.cfg
        src = getattr(cfg, "source_path", None)
        content: bytes
        if src and Path(src).exists():
            content = Path(src).read_bytes()
            self._config_source = Path(src).name
        else:
            content = (json.dumps(config_to_dict(cfg), indent=2,
                                  ensure_ascii=False) + "\n").encode("utf-8")
            self._config_source = None
        (self.path / "config.json").write_bytes(content)
        self._config_sha = _sha256(content)

    def write_sequence(self, text: str) -> None:
        """Archive the exact text of the executed sequence (idempotent: the first
        sequence of the test is authoritative)."""
        if self._has_sequence or not text:
            return
        data = text.encode("utf-8")
        (self.path / "sequence.seq").write_bytes(data)
        self._sequence_sha = _sha256(data)
        self._has_sequence = True
        self._write_metadata()

    # ----------------------------------------------------------------- journal
    def _on_log(self, line: str) -> None:
        try:
            with self._lock:
                if self._journal.closed:
                    return
                self._journal.write(line + "\n")
                self._journal.flush()
        except Exception:
            pass

    # ------------------------------------------------------------------ issue
    def set_issue(self, issue: str, cause: str = "") -> None:
        """Set the test outcome, honoring the severity rank: a more severe
        outcome is never downgraded."""
        with self._lock:
            if _ISSUE_RANK.get(issue, 0) < _ISSUE_RANK.get(self.issue, 0):
                return
            self.issue = issue
            if cause:
                self.cause = cause

    def add_safety_event(self, kind: str, message: str) -> None:
        """Record a timestamped safety event (trip, hard cut-off, comm loss…).

        The ``horodatage`` key is part of the persisted schema — kept as-is."""
        evt = {"horodatage": datetime.now().isoformat(timespec="seconds"),
               "type": kind, "message": message}
        with self._lock:
            self._safety_events.append(evt)
        self._write_metadata()

    def set_conclusion(self, conclusion: str) -> None:
        self.conclusion = conclusion or ""
        self._write_metadata()

    # -------------------------------------------------------------- finalization
    def finalize(self) -> None:
        """Freeze the end timestamp, write the final version of ``essai.json`` and
        unsubscribe from the log. If the outcome stayed ``en_cours`` (clean stop
        without a sequence, or without a trip), it becomes ``termine``."""
        with self._lock:
            already = self.finished_at is not None
            self.finished_at = self.finished_at or datetime.now()
        if not already and self.issue == ISSUE_EN_COURS:
            self.issue = ISSUE_TERMINE
        try:
            self.ctrl.remove_log_listener(self._on_log)
        except Exception:
            pass
        self._write_metadata()
        with self._lock:
            try:
                if not self._journal.closed:
                    self._journal.close()
            except Exception:
                pass

    # -------------------------------------------------------------- metadata
    def _metadata(self) -> dict:
        cadence = {}
        try:
            cadence = {"mesures_s": round(float(self.ctrl._meas_period), 3),
                       "temperature_s": round(float(self.ctrl._temp_period), 3)}
        except Exception:
            cadence = {}
        return {
            "version": __version__,
            "mode": "simulation" if self.simulate else "reel",
            "nom": self.nom,
            "operateur": self.operateur,
            "debut": self.started_at.isoformat(timespec="seconds"),
            "fin": self.finished_at.isoformat(timespec="seconds") if self.finished_at else None,
            "config_source": self._config_source,
            "config_sha256": self._config_sha,
            "sequence_sha256": self._sequence_sha or None,
            "cadences": cadence,
            "conclusion": self.conclusion,
            "issue": {"issue": self.issue, "cause": self.cause},
            "evenements_securite": list(self._safety_events),
        }

    def _write_metadata(self) -> None:
        try:
            (self.path / "essai.json").write_text(
                json.dumps(self._metadata(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        except Exception:
            pass
