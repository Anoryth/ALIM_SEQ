"""Assistant de convertisseur température : schéma du pont diviseur (NTC/PTC),
courbe live tension→°C et éditeur de table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from PySide6 import QtCore, QtGui, QtWidgets

from ..temperature import (NTC_PRESETS, PTC_PRESETS, build_converter,
                           parse_table_csv)
from .plot import CurveView


class DividerSchematic(QtWidgets.QWidget):
    """Schéma du pont diviseur (NTC/PTC) dessiné au QPainter, adapté au thème.

    Les couleurs viennent de la palette (texte/fond) → lisible en clair ET sombre.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.kind = "NTC"          # libellé du capteur
        self.pullup = True          # True : r_series en haut, capteur vers GND

    def set_info(self, kind: str, pullup: bool) -> None:
        self.kind = kind
        self.pullup = pullup
        self.update()

    def paintEvent(self, _evt) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        col = self.palette().color(QtGui.QPalette.WindowText)
        p.setPen(QtGui.QPen(col, 2))
        f = p.font(); f.setPointSize(9); p.setFont(f)

        W = self.width()
        x = 70                      # axe vertical du pont
        top, bot = 18, self.height() - 22
        y1 = top + 28               # haut composant 1
        y2 = (top + bot) // 2 - 16  # bas composant 1 / nœud au milieu
        ynode = (top + bot) // 2
        y3 = ynode + 16             # haut composant 2
        y4 = bot - 22               # bas composant 2

        upper = "r_series" if self.pullup else self.kind
        lower = self.kind if self.pullup else "r_series"

        def box(yA, yB, label, sensor):
            p.drawLine(x, yA, x, yB)
            rect = QtCore.QRect(x - 16, yA + 4, 32, yB - yA - 8)
            p.drawRect(rect)
            if sensor:  # symbole thermistance : flèche diagonale
                p.drawLine(rect.left() - 6, rect.bottom() + 6, rect.right() + 6, rect.top() - 6)
            p.drawText(QtCore.QRect(x + 22, yA, W - x - 30, yB - yA),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, label)

        # Vréf en haut
        p.drawText(QtCore.QRect(x - 40, top - 4, 80, 16), QtCore.Qt.AlignCenter, self.tr("Vref"))
        p.drawLine(x, top + 12, x, y1)
        box(y1, y2, upper, sensor=(upper == self.kind))
        # nœud + dérivation vers l'ADC
        p.drawLine(x, y2, x, y3)
        p.setBrush(col); p.drawEllipse(QtCore.QPoint(x, ynode), 3, 3); p.setBrush(QtCore.Qt.NoBrush)
        p.drawLine(x, ynode, x + 120, ynode)
        p.drawText(QtCore.QRect(x + 124, ynode - 9, W - x - 130, 18),
                   QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.tr("→ ai (measured)"))
        box(y3, y4, lower, sensor=(lower == self.kind))
        # GND
        p.drawLine(x, y4, x, bot - 6)
        for i, w in enumerate((16, 10, 4)):
            p.drawLine(x - w, bot - 6 + i * 4, x + w, bot - 6 + i * 4)


class ConverterAssistant(QtWidgets.QDialog):
    """Assistant de convertisseur température : schéma (NTC/PTC), **courbe live**
    tension→°C ([CurveView], sans dépendance) et **éditeur de table** à deux
    colonnes. Génère le bloc JSON ``converter``."""

    _FIELDS = {
        "ntc": [("r0", "10000"), ("t0", "25"), ("beta", "3950"),
                ("r_series", "10000"), ("v_ref", "3.3"), ("pullup_to_vref", "true"),
                ("fault_margin", "0.02")],
        "ptc": [("r0", "1000"), ("t0", "0"), ("alpha", "0.00385"),
                ("r_series", "1000"), ("v_ref", "3.3"), ("pullup_to_vref", "true"),
                ("fault_margin", "0.02")],
        "poly": [("coeffs", "[0, 30]")],
        "thermocouple": [("tc_type", "K"), ("cjc_c", "25"), ("gain", "1.0"),
                         ("offset_mv", "0.0")],
        "identity": [],
    }
    _STR_KEYS = {"tc_type"}
    _DEFAULT_POINTS = [[0.20, 100.0], [0.60, 60.0], [1.00, 40.0],
                       [1.60, 25.0], [2.40, 0.0], [3.00, -20.0]]
    # Plage de température PLAUSIBLE par type : on n'affiche la courbe que là où elle
    # est physiquement utile (sinon les asymptotes NTC/PTC divergent et écrasent
    # l'échelle, rendant le graphe illisible).
    _T_BOUNDS = {
        "ntc": (-60.0, 300.0),
        "ptc": (-100.0, 600.0),
        "thermocouple": (-50.0, 800.0),
        "poly": (-100.0, 500.0),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Temperature converter assistant"))
        self.resize(780, 580)
        root = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["ntc", "ptc", "thermocouple", "table", "poly", "identity"])
        self.type_combo.currentTextChanged.connect(self._on_type)
        form.addRow(self.tr("Type"), self.type_combo)
        root.addLayout(form)

        mid = QtWidgets.QHBoxLayout()
        left = QtWidgets.QVBoxLayout()
        self.schema = DividerSchematic()
        self.schema.setMinimumWidth(250)
        left.addWidget(self.schema)
        self.params_host = QtWidgets.QWidget()
        self.params_layout = QtWidgets.QVBoxLayout(self.params_host)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        left.addWidget(self.params_host)
        left.addStretch(1)
        mid.addLayout(left, 0)
        self.curve = CurveView()
        mid.addWidget(self.curve, 1)
        root.addLayout(mid, 1)

        self.edits: Dict[str, QtWidgets.QWidget] = {}
        self.points_table: QtWidgets.QTableWidget = None
        self.json_line = QtWidgets.QLineEdit(); self.json_line.setReadOnly(True)
        root.addWidget(self.json_line)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        copy = btns.addButton(self.tr("Copy the JSON"), QtWidgets.QDialogButtonBox.ActionRole)
        copy.clicked.connect(self._copy)
        root.addWidget(btns)

        self._on_type("ntc")

    def _clear_params(self) -> None:
        self.edits = {}
        self.points_table = None
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)   # retrait immédiat de l'affichage
                w.deleteLater()

    def _on_type(self, t: str) -> None:
        self._clear_params()
        if t == "table":
            box = QtWidgets.QGroupBox(self.tr("Calibration points (voltage → °C)"))
            bl = QtWidgets.QVBoxLayout(box)
            self.points_table = QtWidgets.QTableWidget(0, 2)
            self.points_table.setHorizontalHeaderLabels([self.tr("Voltage (V)"), "°C"])
            self.points_table.horizontalHeader().setStretchLastSection(True)
            self.points_table.cellChanged.connect(lambda *_: self._update())
            bl.addWidget(self.points_table)
            hb = QtWidgets.QHBoxLayout()
            add = QtWidgets.QPushButton(self.tr("+ Point")); add.clicked.connect(lambda: self._add_point())
            rem = QtWidgets.QPushButton(self.tr("− Point")); rem.clicked.connect(self._del_point)
            imp = QtWidgets.QPushButton(self.tr("Import CSV…")); imp.clicked.connect(self._import_csv)
            hb.addWidget(add); hb.addWidget(rem); hb.addWidget(imp); hb.addStretch(1)
            bl.addLayout(hb)
            self.params_layout.addWidget(box)
            for v, tc in self._DEFAULT_POINTS:
                self._add_point(v, tc)
        else:
            box = QtWidgets.QGroupBox(self.tr("Parameters"))
            fl = QtWidgets.QFormLayout(box)
            presets = {"ntc": NTC_PRESETS, "ptc": PTC_PRESETS}.get(t)
            if presets:
                combo = QtWidgets.QComboBox()
                combo.addItem(self.tr("— preset —"))
                combo.addItems(list(presets))
                combo.currentTextChanged.connect(
                    lambda name, p=presets: self._apply_preset(p.get(name)))
                fl.addRow(self.tr("Preset"), combo)
            for key, default in self._FIELDS.get(t, []):
                e = QtWidgets.QLineEdit(default)
                e.textChanged.connect(self._update)
                fl.addRow(key, e)
                self.edits[key] = e
            self.params_layout.addWidget(box)
        self.schema.setVisible(t in ("ntc", "ptc"))
        self._update()

    def _add_point(self, v: float = 1.0, tc: float = 25.0) -> None:
        t = self.points_table
        t.blockSignals(True)
        r = t.rowCount(); t.insertRow(r)
        t.setItem(r, 0, QtWidgets.QTableWidgetItem(str(v)))
        t.setItem(r, 1, QtWidgets.QTableWidgetItem(str(tc)))
        t.blockSignals(False)
        self._update()

    def _del_point(self, *_) -> None:
        t = self.points_table
        r = t.currentRow() if t.currentRow() >= 0 else t.rowCount() - 1
        if r >= 0:
            t.removeRow(r)
        self._update()

    def _apply_preset(self, preset) -> None:
        if not preset:
            return
        for key, val in preset.items():
            if key in self.edits:
                self.edits[key].setText(str(val))
        self._update()

    def _import_csv(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.tr("Import a calibration table"), "", self.tr("CSV (*.csv *.txt);;All (*)"))
        if not path:
            return
        try:
            pts = parse_table_csv(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("CSV import"), str(exc))
            return
        self.points_table.setRowCount(0)
        for v, tc in pts:
            self._add_point(v, tc)

    def set_converter(self, d: dict) -> None:
        """Pré-remplit l'assistant à partir d'un bloc ``converter`` existant."""
        t = d.get("type", "ntc")
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentText(t)
        self.type_combo.blockSignals(False)
        self._on_type(t)
        if t == "table":
            self.points_table.blockSignals(True)
            self.points_table.setRowCount(0)
            for v, tc in d.get("points", []):
                self._add_point(float(v), float(tc))
            self.points_table.blockSignals(False)
        else:
            for key, e in self.edits.items():
                if key in d:
                    val = d[key]
                    if key == "coeffs":
                        e.setText(json.dumps(val))
                    elif key == "pullup_to_vref":
                        e.setText("true" if val else "false")
                    else:
                        e.setText(str(val))
        self._update()

    def converter_dict(self) -> dict:
        t = self.type_combo.currentText()
        d: dict = {"type": t}
        if t == "table":
            pts = []
            for r in range(self.points_table.rowCount()):
                vi, ti = self.points_table.item(r, 0), self.points_table.item(r, 1)
                if vi and ti and vi.text().strip() and ti.text().strip():
                    pts.append([float(vi.text().replace(",", ".")),
                                float(ti.text().replace(",", "."))])
            pts.sort(key=lambda p: p[0])
            d["points"] = pts
            return d
        for key, e in self.edits.items():
            txt = e.text().strip()
            if key == "coeffs":
                d[key] = json.loads(txt)
            elif key == "pullup_to_vref":
                d[key] = txt.lower() in ("1", "true", "vrai", "oui")
            elif key in self._STR_KEYS:
                d[key] = txt
            else:
                d[key] = float(txt)
        return d

    def _v_range(self, d: dict):
        t = d["type"]
        if t in ("ntc", "ptc"):
            vr = d.get("v_ref", 3.3)
            return 0.02, max(0.1, vr - 0.02)
        if t == "thermocouple":
            return 0.0, 0.021       # 0–21 mV ≈ 0–500 °C (type K)
        if t == "table":
            vs = [p[0] for p in d["points"]] or [0.0, 3.3]
            return min(vs), max(vs)
        return 0.0, 5.0

    def _update(self) -> None:
        try:
            d = self.converter_dict()
            conv = build_converter(d)
            self.json_line.setText(json.dumps(d, ensure_ascii=False))
            if d["type"] in ("ntc", "ptc"):
                self.schema.set_info(d["type"].upper(), bool(d.get("pullup_to_vref", True)))
            v0, v1 = self._v_range(d)
            lo, hi = self._T_BOUNDS.get(d["type"], (-273.0, 5000.0))
            xs, ys = [], []
            for k in range(400):
                v = v0 + (v1 - v0) * k / 399
                tv = conv.to_celsius(v)
                # On ne garde que la portion dans la plage de fonctionnement plausible.
                if tv == tv and lo <= tv <= hi:
                    xs.append(v); ys.append(tv)
            markers = d["points"] if d["type"] == "table" else None
            self.curve.set_data(xs, ys, markers)
        except Exception as exc:
            self.json_line.setText(f"(incomplet) {exc}")
            self.curve.set_data([], [])

    def _copy(self) -> None:
        QtWidgets.QApplication.clipboard().setText(
            json.dumps(self.converter_dict(), ensure_ascii=False))
