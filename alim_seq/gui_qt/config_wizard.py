"""Assistant de configuration : au premier lancement (ou à la demande), aide à
partir de zéro. Deux voies :

- **Simulation** : génère une configuration minimale sans matériel.
- **Scan VISA** : détecte les alimentations branchées (``scan_instruments``) et
  prépare ``supplies`` + ``channels`` pré-remplis.

Le résultat (dict de config brut) est renvoyé via ``result_config`` ; la fenêtre
principale le charge dans l'éditeur de configuration pour revue avant application —
l'assistant ne pilote jamais le matériel directement.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..psu import (available_models, probe_instrument, psu_channel_count,
                   psu_model_limits, scan_instruments)
from . import theme
from .workers import Task


def _sim_config() -> dict:
    """Config minimale de simulation : une HMP4040, deux voies CH1/CH2."""
    return {
        "simulate": True,
        "supplies": {"PSU1": {"model": "HMP4040"}},
        "channels": {
            "CH1": {"supply": "PSU1", "channel": 1, "max_voltage": 32, "max_current": 10},
            "CH2": {"supply": "PSU1", "channel": 2, "max_voltage": 32, "max_current": 10},
        },
        "temperatures": {},
        "safety": {},
    }


def _guess_model(idn: str) -> str:
    """Devine le modèle depuis l'IDN (``*IDN?``) ; défaut HMP4040."""
    up = (idn or "").upper()
    for m in available_models():
        if m.upper() in up:
            return m
    return "HMP4040"


class ConfigWizard(QtWidgets.QDialog):
    """Assistant de configuration du banc. ``result_config`` porte le dict généré
    (ou reste ``None`` si annulé)."""

    _COLS = ["Inclure", "Nom", "Modèle", "Adresse VISA (IDN)"]

    def __init__(self, parent=None, visa_backend: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Assistant de configuration")
        self.resize(720, 460)
        self.result_config = None
        self._visa_backend = visa_backend
        self._task = None

        v = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "Bienvenue. Cet assistant prépare une configuration de départ.<br>"
            "• <b>Sans matériel</b> : générez une configuration de <b>simulation</b>.<br>"
            "• <b>Avec matériel</b> : <b>scannez</b> les alimentations VISA branchées, "
            "cochez celles à inclure, puis générez.")
        intro.setTextFormat(QtCore.Qt.RichText)
        intro.setWordWrap(True)
        v.addWidget(intro)

        row = QtWidgets.QHBoxLayout()
        self.btn_scan = QtWidgets.QPushButton("🔎 Scanner le matériel VISA")
        self.btn_scan.setToolTip("Détecte l'USB-TMC et le LAN VXI-11. Un HMP en mode "
                                 "socket LAN (::5025::SOCKET) n'est PAS découvrable : "
                                 "utiliser « Ajouter une adresse manuelle ».")
        self.btn_scan.clicked.connect(self._scan)
        row.addWidget(self.btn_scan)
        self.btn_manual = QtWidgets.QPushButton("➕ Ajouter une adresse manuelle…")
        self.btn_manual.setToolTip("Saisir et tester une adresse VISA connue "
                                   "(ex. socket LAN TCPIP0::IP::5025::SOCKET).")
        self.btn_manual.clicked.connect(self._add_manual)
        row.addWidget(self.btn_manual)
        self.scan_status = QtWidgets.QLabel("")
        self.scan_status.setStyleSheet(theme.style("text.muted"))
        row.addWidget(self.scan_status)
        row.addStretch(1)
        v.addLayout(row)

        self.table = QtWidgets.QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(self._COLS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 120)
        v.addWidget(self.table, 1)

        btns = QtWidgets.QHBoxLayout()
        sim = QtWidgets.QPushButton("Configuration de simulation")
        sim.setToolTip("Génère une config sans matériel (une HMP4040, CH1/CH2).")
        sim.clicked.connect(self._use_simulation)
        btns.addWidget(sim)
        btns.addStretch(1)
        self.btn_generate = QtWidgets.QPushButton("Générer la configuration")
        self.btn_generate.setDefault(True)
        self.btn_generate.setEnabled(False)
        self.btn_generate.clicked.connect(self._generate)
        btns.addWidget(self.btn_generate)
        cancel = QtWidgets.QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        v.addLayout(btns)

    # ---------------------------------------------------------------- scan VISA
    def _scan(self) -> None:
        self.btn_scan.setEnabled(False)
        self.scan_status.setText("Scan en cours… (quelques secondes)")
        backend = self._visa_backend
        self._task = Task(lambda: scan_instruments(visa_backend=backend), self)
        self._task.done.connect(self._scan_done)
        self._task.failed.connect(self._scan_failed)
        self._task.start()

    def _scan_failed(self, msg: str) -> None:
        self.btn_scan.setEnabled(True)
        self.scan_status.setText(f"Scan impossible : {msg}")
        self.scan_status.setStyleSheet(theme.style("text.error"))

    def _scan_done(self, found) -> None:
        self.btn_scan.setEnabled(True)
        found = list(found or [])
        self.scan_status.setText(
            f"{len(found)} instrument(s) détecté(s)." if found
            else "Aucun instrument détecté — vérifier câblage/VISA, ou utiliser la simulation.")
        self.scan_status.setStyleSheet(theme.style("text.muted"))
        self.table.setRowCount(0)
        for i, inst in enumerate(found, start=1):
            self._add_row(f"PSU{i}", _guess_model(inst.get("idn", "")),
                          inst.get("resource", ""), inst.get("idn", ""))
        self.btn_generate.setEnabled(self.table.rowCount() > 0)

    # ------------------------------------------------------- adresse manuelle
    def _add_manual(self) -> None:
        """Saisir une adresse VISA connue (typiquement un socket LAN, non découvrable
        par le scan) et la tester via ``*IDN?`` avant de l'ajouter."""
        addr, ok = QtWidgets.QInputDialog.getText(
            self, "Ajouter une adresse manuelle",
            "Adresse VISA (ex. socket LAN, USB) :",
            text="TCPIP0::192.168.0.11::5025::SOCKET")
        if not ok or not addr.strip():
            return
        addr = addr.strip()
        self.btn_manual.setEnabled(False)
        self.scan_status.setText(f"Test de {addr}…")
        self.scan_status.setStyleSheet(theme.style("text.muted"))
        self._task = Task(lambda: probe_instrument(addr, self._visa_backend), self)
        self._task.done.connect(lambda idn: self._manual_ok(addr, idn))
        self._task.failed.connect(lambda m: self._manual_failed(addr, m))
        self._task.start()

    def _manual_ok(self, addr, idn) -> None:
        self.btn_manual.setEnabled(True)
        self.scan_status.setText(f"✓ {addr} — {idn}")
        self.scan_status.setStyleSheet(theme.style("text.ok"))
        self._add_row(f"PSU{self.table.rowCount() + 1}", _guess_model(idn), addr, idn)
        self.btn_generate.setEnabled(True)

    def _manual_failed(self, addr, msg) -> None:
        self.btn_manual.setEnabled(True)
        self.scan_status.setText("")
        r = QtWidgets.QMessageBox.question(
            self, "Ajouter une adresse manuelle",
            f"Pas de réponse de {addr} :\n{msg}\n\n"
            "Ajouter quand même cette adresse (à tester plus tard) ?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if r == QtWidgets.QMessageBox.Yes:
            self._add_row(f"PSU{self.table.rowCount() + 1}", "HMP4040", addr, "")
            self.btn_generate.setEnabled(True)
            self.scan_status.setText(f"Adresse ajoutée sans test : {addr}")
            self.scan_status.setStyleSheet(theme.style("text.muted"))

    def _add_row(self, name, model, resource, idn) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        chk = QtWidgets.QTableWidgetItem()
        chk.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
        chk.setCheckState(QtCore.Qt.Checked)
        self.table.setItem(r, 0, chk)
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(name))
        combo = QtWidgets.QComboBox()
        combo.addItems(available_models())
        idx = combo.findText(model)
        combo.setCurrentIndex(max(0, idx))
        self.table.setCellWidget(r, 2, combo)
        addr = QtWidgets.QTableWidgetItem(resource + (f"   ({idn})" if idn else ""))
        addr.setData(QtCore.Qt.UserRole, resource)
        self.table.setItem(r, 3, addr)

    # ---------------------------------------------------------------- génération
    def _use_simulation(self) -> None:
        self.result_config = _sim_config()
        self.accept()

    def _generate(self) -> None:
        supplies, channels = {}, {}
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() != QtCore.Qt.Checked:
                continue
            name = (self.table.item(r, 1).text() or f"PSU{r + 1}").strip()
            model = self.table.cellWidget(r, 2).currentText()
            resource = self.table.item(r, 3).data(QtCore.Qt.UserRole) or ""
            supplies[name] = {"model": model, "resource": resource}
            limits = psu_model_limits(model) or (32.0, 10.0, 160.0)
            n = psu_channel_count(model) or 4
            for ch in range(1, n + 1):
                channels[f"{name}_CH{ch}"] = {
                    "supply": name, "channel": ch,
                    "max_voltage": limits[0], "max_current": limits[1],
                }
        if not supplies:
            QtWidgets.QMessageBox.information(
                self, "Assistant", "Cochez au moins une alimentation à inclure.")
            return
        self.result_config = {
            "simulate": False, "supplies": supplies, "channels": channels,
            "temperatures": {}, "safety": {},
        }
        self.accept()
