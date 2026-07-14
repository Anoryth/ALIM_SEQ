"""Relecture d'un essai : rejoue les courbes d'un dossier ``logs/essais/…``.

Transforme l'application d'un simple enregistreur en outil d'analyse. On **réutilise**
au maximum l'existant :

- lecture du CSV et mise en séries : ``rapport._read_csv`` / ``_series_from_csv`` ;
- événements horodatés (repères) : ``rapport.evenements`` (mêmes que les badges du
  rapport) ;
- tracé + curseur + légende cliquable + marqueurs : :class:`~alim_seq.gui_qt.plot.TempPlotQt`,
  dont :class:`EssaiReplayView` hérite en **remplissant les buffers depuis le CSV**
  (statique) au lieu de les streamer.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..rapport import _read_csv, _series_from_csv, evenements
from .plot import TempPlotQt


class EssaiReplayView(TempPlotQt):
    """Vue statique d'un essai enregistré : mêmes interactions que le graphe live
    (bascule °C/A/V, curseur de lecture, légende cliquable, repères d'événements),
    mais alimentée par le ``mesures.csv`` du dossier plutôt que par le flux temps réel."""

    def __init__(self, dossier, parent=None):
        dossier = Path(dossier)
        header, rows = _read_csv(dossier)
        temp = _series_from_csv(header, rows, "_C")
        volt = _series_from_csv(header, rows, "_Vmeas")
        curr = _series_from_csv(header, rows, "_Imeas")
        sensors = list(temp.keys())
        channels = list(volt.keys())
        warn, crit = self._thresholds(dossier)
        super().__init__(sensors, warn, crit, channels=channels, parent=parent)
        # Remplit directement les buffers (relecture statique, pas de flux).
        self._series["temp"] = {k: deque(v) for k, v in temp.items()}
        self._series["voltage"] = {k: deque(v) for k, v in volt.items()}
        self._series["current"] = {k: deque(v) for k, v in curr.items()}
        # Fenêtre = durée totale -> tout l'essai est visible (pas de glissement).
        dur = 0.0
        for grp in self._series.values():
            for dq in grp.values():
                if dq:
                    dur = max(dur, dq[-1][0])
        self.window_s = max(1.0, dur)
        # Événements -> repères verticaux numérotés (comme les badges du rapport).
        self.evenements = evenements(str(dossier), header, rows)
        self._marks = [(e["t_s"], str(i + 1)) for i, e in enumerate(self.evenements)]
        # Mode initial : températures si des capteurs existent, sinon courants.
        self.set_mode("temp" if sensors else "current")

    def push(self, *args, **kwargs) -> None:  # relecture statique : ignore tout flux
        return

    @staticmethod
    def _thresholds(dossier):
        """Seuils warning/critical par capteur, lus dans la config archivée de l'essai
        (lecture tolérante : un fichier absent/ancien ne casse pas la relecture)."""
        warn, crit = {}, {}
        try:
            cfg = json.loads((Path(dossier) / "config.json").read_text(encoding="utf-8"))
            for name, t in (cfg.get("temperatures") or {}).items():
                warn[name] = t.get("warning")
                crit[name] = t.get("critical")
        except Exception:
            pass
        return warn, crit


class EssaiCompareView(TempPlotQt):
    """Superpose les courbes de **deux** essais (recalées sur t = 0) dans un même
    repère, pour visualiser une dérive avant/après. Les séries sont préfixées par un
    tag (``A·CH1``, ``B·CH1``) — une couleur par série, légende cliquable pour isoler."""

    def __init__(self, dossier_a, dossier_b, tag_a="A", tag_b="B", parent=None):
        a = self._one(dossier_a)
        b = self._one(dossier_b)

        def merge(key):
            out = {}
            for tag, src in ((tag_a, a), (tag_b, b)):
                for name, pts in src[key].items():
                    out[f"{tag}·{name}"] = pts
            return out

        temp, volt, curr = merge("temp"), merge("volt"), merge("curr")
        warn, crit = {}, {}
        for tag, src in ((tag_a, a), (tag_b, b)):
            for name, val in src["warn"].items():
                warn[f"{tag}·{name}"] = val
            for name, val in src["crit"].items():
                crit[f"{tag}·{name}"] = val

        super().__init__(list(temp.keys()), warn, crit,
                         channels=list(volt.keys()), parent=parent)
        self._series["temp"] = {k: deque(v) for k, v in temp.items()}
        self._series["voltage"] = {k: deque(v) for k, v in volt.items()}
        self._series["current"] = {k: deque(v) for k, v in curr.items()}
        dur = 0.0
        for grp in self._series.values():
            for dq in grp.values():
                if dq:
                    dur = max(dur, dq[-1][0])
        self.window_s = max(1.0, dur)
        self._marks = []   # pas d'événements en comparaison (lisibilité)
        self.set_mode("temp" if temp else "current")

    def push(self, *args, **kwargs) -> None:  # comparaison statique
        return

    @staticmethod
    def _one(dossier):
        dossier = Path(dossier)
        header, rows = _read_csv(dossier)
        warn, crit = EssaiReplayView._thresholds(dossier)
        return {"temp": _series_from_csv(header, rows, "_C"),
                "volt": _series_from_csv(header, rows, "_Vmeas"),
                "curr": _series_from_csv(header, rows, "_Imeas"),
                "warn": warn, "crit": crit}


def _mode_combo(view) -> QtWidgets.QComboBox:
    """Sélecteur de grandeur commun aux vues de relecture/comparaison."""
    qty = QtWidgets.QComboBox()
    if view.sensors:
        qty.addItem(QtCore.QCoreApplication.translate("replay", "Temperatures (°C)"), "temp")
    qty.addItem(QtCore.QCoreApplication.translate("replay", "Currents (A)"), "current")
    qty.addItem(QtCore.QCoreApplication.translate("replay", "Voltages (V)"), "voltage")
    qty.currentIndexChanged.connect(lambda i: view.set_mode(qty.itemData(i)))
    return qty


def _meta_header(meta: dict, dossier: Path) -> str:
    """Ligne d'en-tête HTML : nom, dates, mode, issue de l'essai."""
    issue = (meta.get("issue") or {}).get("issue", "?")
    parts = [f"<b>{meta.get('nom') or dossier.name}</b>"]
    if meta.get("operateur"):
        parts.append(QtCore.QCoreApplication.translate("replay", "operator {}").format(meta["operateur"]))
    if meta.get("debut"):
        parts.append(QtCore.QCoreApplication.translate("replay", "start {}").format(meta["debut"]))
    if meta.get("fin"):
        parts.append(QtCore.QCoreApplication.translate("replay", "end {}").format(meta["fin"]))
    parts.append(QtCore.QCoreApplication.translate("replay", "mode {}").format(meta.get("mode", "?")))
    parts.append(QtCore.QCoreApplication.translate("replay", "outcome: {}").format(issue))
    return " · ".join(parts)


def _events_legend(evs) -> QtWidgets.QWidget:
    """Légende repliable des événements numérotés (n° = repère sur le graphe)."""
    box = QtWidgets.QGroupBox(QtCore.QCoreApplication.translate("replay", "Events ({})").format(len(evs)))
    box.setCheckable(True)
    box.setChecked(False)
    lay = QtWidgets.QVBoxLayout(box)
    txt = QtWidgets.QLabel("<br>".join(
        f"<b>{i + 1}</b> · {e['t_s']:.1f}s · {e['msg']}" for i, e in enumerate(evs)))
    txt.setTextFormat(QtCore.Qt.RichText)
    txt.setWordWrap(True)
    txt.setVisible(False)
    box.toggled.connect(txt.setVisible)
    lay.addWidget(txt)
    return box


def open_replay_dialog(parent, dossier, on_report=None) -> QtWidgets.QDialog:
    """Construit et affiche (non modal) la fenêtre de relecture d'un essai.

    ``on_report(dossier)`` (optionnel) est branché sur un bouton « Générer le
    rapport » — le parent y met sa propre logique (demande de conclusion + tâche)."""
    dossier = Path(dossier)
    meta = {}
    try:
        meta = json.loads((dossier / "essai.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(QtCore.QCoreApplication.translate("replay", "Replay — {}").format(dossier.name))
    dlg.resize(920, 580)
    v = QtWidgets.QVBoxLayout(dlg)

    hdr = QtWidgets.QLabel(_meta_header(meta, dossier))
    hdr.setTextFormat(QtCore.Qt.RichText)
    hdr.setWordWrap(True)
    v.addWidget(hdr)

    view = EssaiReplayView(dossier)

    bar = QtWidgets.QHBoxLayout()
    bar.addWidget(QtWidgets.QLabel(QtCore.QCoreApplication.translate("replay", "Quantity:")))
    bar.addWidget(_mode_combo(view))
    bar.addStretch(1)
    png = QtWidgets.QPushButton("📷 PNG")
    png.clicked.connect(lambda: _save_png(dlg, view))
    bar.addWidget(png)
    if on_report is not None:
        rb = QtWidgets.QPushButton(QtCore.QCoreApplication.translate("replay", "📄 Generate the PDF report"))
        rb.clicked.connect(lambda: on_report(dossier))
        bar.addWidget(rb)
    v.addLayout(bar)

    v.addWidget(view, 1)
    if view.evenements:
        v.addWidget(_events_legend(view.evenements))

    dlg.setModal(False)
    dlg.show()
    return dlg


def open_compare_dialog(parent, dossier_a, dossier_b) -> QtWidgets.QDialog:
    """Affiche (non modal) la fenêtre de comparaison de deux essais (courbes
    superposées, recalées sur t = 0)."""
    dossier_a, dossier_b = Path(dossier_a), Path(dossier_b)
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(QtCore.QCoreApplication.translate("replay", "Comparison — {} vs {}").format(dossier_a.name, dossier_b.name))
    dlg.resize(940, 600)
    v = QtWidgets.QVBoxLayout(dlg)

    hdr = QtWidgets.QLabel(
        QtCore.QCoreApplication.translate("replay", "<b>A</b> = {} &nbsp;·&nbsp; <b>B</b> = {} &nbsp;—&nbsp; "
             "curves aligned on t = 0 (one color per series; click a legend entry "
             "to isolate it)").format(dossier_a.name, dossier_b.name))
    hdr.setTextFormat(QtCore.Qt.RichText)
    hdr.setWordWrap(True)
    v.addWidget(hdr)

    view = EssaiCompareView(dossier_a, dossier_b)
    bar = QtWidgets.QHBoxLayout()
    bar.addWidget(QtWidgets.QLabel(QtCore.QCoreApplication.translate("replay", "Quantity:")))
    bar.addWidget(_mode_combo(view))
    bar.addStretch(1)
    png = QtWidgets.QPushButton("📷 PNG")
    png.clicked.connect(lambda: _save_png(dlg, view))
    bar.addWidget(png)
    v.addLayout(bar)
    v.addWidget(view, 1)

    dlg.setModal(False)
    dlg.show()
    return dlg


def _save_png(parent, view) -> None:
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        parent, QtCore.QCoreApplication.translate("replay", "Export the chart"), "relecture.png", QtCore.QCoreApplication.translate("replay", "PNG image (*.png)"))
    if not path:
        return
    if not path.lower().endswith(".png"):
        path += ".png"
    view.grab().save(path)
