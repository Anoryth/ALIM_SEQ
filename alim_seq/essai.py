"""Dossier d'essai autonome : un enregistrement = un dossier re-exploitable.

Chaque démarrage d'enregistrement crée ``logs/essais/AAAAMMJJ_HHMMSS[_<nom>]/``
qui regroupe TOUT ce qu'il faut pour régénérer un rapport bien plus tard, sans
l'application ouverte sur l'essai :

- ``mesures.csv``  : le CSV des mesures (écrit par le contrôleur) ;
- ``config.json``  : copie à l'identique de la configuration active ;
- ``sequence.seq`` : texte exact de la séquence exécutée (absent si pilotage
  purement manuel) ;
- ``journal.log``  : événements du contrôleur pendant l'essai ;
- ``essai.json``   : métadonnées (version, mode, horodatages, empreintes, issue,
  événements de sécurité).

Ce module ne dépend PAS de Qt : il est testable seul. Le contrôleur lui délègue
la tenue du dossier au fil de l'essai.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import __version__

# Issues possibles d'un essai, du moins au plus grave. Le rang sert de garde
# anti-déclassement : une issue plus grave ne peut pas être écrasée par une
# moins grave (un déclenchement de sécurité reste inscrit même si la
# désalimentation se « termine » ensuite proprement).
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
    """Nettoie un nom d'essai pour en faire un composant de dossier sûr :
    espaces -> ``_``, caractères interdits ``/\\:*?"<>|`` retirés, contrôle
    supprimé. Retourne "" si rien d'exploitable ne subsiste."""
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
    # Comprime les tirets bas multiples, retire ceux de bord et les points de bord
    # (un dossier ne devrait pas commencer par un point ni finir par un espace/point).
    name = "".join(out).strip("_. ")
    while "__" in name:
        name = name.replace("__", "_")
    return name


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DossierEssai:
    """Tient le dossier d'un essai en cours. Créé par ``start_recording`` et
    finalisé par ``stop_recording`` (ou ``close``) côté contrôleur."""

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
        # Anti-collision : l'horodatage est à la seconde — deux essais démarrés dans
        # la même seconde (stop/start rapide) partageraient le dossier et le second
        # ÉCRASERAIT mesures.csv. On suffixe _2, _3… ; mkdir(exist_ok=False) rend le
        # test-et-création atomique (pas de TOCTOU entre deux instances).
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
        # S'abonne au journal du contrôleur le temps de l'essai.
        self.ctrl.add_log_listener(self._on_log)
        # Écrit une première version d'essai.json (issue = en_cours) : le dossier
        # est déjà exploitable même si l'application est tuée en cours d'essai.
        self._write_metadata()

    # ------------------------------------------------------------- archivage
    def _archive_config(self) -> None:
        """Copie la configuration active dans ``config.json`` et calcule son
        empreinte. Copie octet pour octet si la config vient d'un fichier
        (``source_path``), sinon sérialise l'état mémoire."""
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
        """Archive le texte exact de la séquence exécutée (idempotent : la
        première séquence de l'essai fait foi)."""
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
        """Fixe l'issue de l'essai en respectant le rang de gravité : une issue
        plus grave n'est jamais déclassée."""
        with self._lock:
            if _ISSUE_RANK.get(issue, 0) < _ISSUE_RANK.get(self.issue, 0):
                return
            self.issue = issue
            if cause:
                self.cause = cause

    def add_safety_event(self, kind: str, message: str) -> None:
        """Consigne un événement de sécurité horodaté (trip, coupure dure,
        perte de comm…)."""
        evt = {"horodatage": datetime.now().isoformat(timespec="seconds"),
               "type": kind, "message": message}
        with self._lock:
            self._safety_events.append(evt)
        self._write_metadata()

    def set_conclusion(self, conclusion: str) -> None:
        self.conclusion = conclusion or ""
        self._write_metadata()

    # -------------------------------------------------------------- finalisation
    def finalize(self) -> None:
        """Fige l'horodatage de fin, écrit la version finale d'``essai.json`` et
        se désabonne du journal. Si l'issue est restée ``en_cours`` (arrêt propre
        sans séquence, ou sans trip), elle devient ``termine``."""
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

    # -------------------------------------------------------------- métadonnées
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
