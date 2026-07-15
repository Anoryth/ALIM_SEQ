"""Onglet Configuration : tables alims/voies/groupes/capteurs, scan VISA, test
de connexion, sous-onglet Avancé JSON. Greffé sur la fenêtre (ConfigMixin)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import List

from PySide6 import QtCore, QtGui, QtWidgets

from ..config import load_config
from ..controller import Controller
from ..instrument import driver_role
from ..psu import available_models, scan_instruments
from . import theme
from .converter import ConverterAssistant


class ConfigMixin:
    """Onglet Configuration, greffé sur :class:`AlimSeqQtGUI`."""

    # Column descriptions: (JSON key, displayed label, tooltip). Order is
    # authoritative for the column <-> key mapping (no raw key is ever shown).
    # These are methods (not class attributes) so labels/tooltips translate at
    # build time, once the language is known.
    def _sup_cols(self):
        tr = self.tr
        return [
            ("name", tr("Name"), tr("Logical name of the supply (JSON key: supplies.<name>).")),
            ("model", tr("Model"), tr("R&S HMP model (JSON key: model).")),
            ("resource", tr("VISA address"),
             tr("VISA resource, e.g. TCPIP0::192.168.0.10::5025::SOCKET (JSON key: resource).")),
        ]

    def _ch_cols(self):
        tr = self.tr
        return [
            ("label", tr("Label"), tr("Channel name, used everywhere in the app (JSON key: channels.<label>).")),
            ("supply", tr("Supply"), tr("Supply that carries the channel (JSON key: supply).")),
            ("channel", tr("Channel"), tr("Physical channel 1..N of the supply (JSON key: channel).")),
            ("negative", tr("Negative rail"),
             tr("Channel wired in reverse to produce a negative voltage (JSON key: negative).")),
            ("default_voltage", tr("Initial V (V)"), tr("Setpoint voltage at startup (JSON key: default_voltage).")),
            ("default_current", tr("Initial I (A)"), tr("Current limit at startup (JSON key: default_current).")),
            ("max_voltage", tr("V max (V)"), tr("Maximum voltage allowed for the channel (JSON key: max_voltage).")),
            ("max_current", tr("I max (A)"), tr("Maximum current allowed for the channel (JSON key: max_current).")),
        ]

    def _gp_cols(self):
        tr = self.tr
        return [
            ("nom", tr("Name"), tr("Name of the series group, driveable like a channel (JSON key: groups.<name>).")),
            ("members", tr("Member channels"), tr("Channels in series, comma-separated (JSON key: members).")),
            ("split", tr("Split"),
             tr("Voltage split: balanced (equal) or fill (fill). JSON key: split.")),
            ("max_voltage", tr("V max (V) — 0 = auto"),
             tr("Group max voltage; 0 = sum of members (JSON key: max_voltage).")),
            ("max_current", tr("I max (A) — 0 = auto"),
             tr("Group max current; 0 = smallest of the members (JSON key: max_current).")),
        ]

    def _tp_cols(self):
        tr = self.tr
        return [
            ("nom", tr("Name"), tr("Sensor name (JSON key: temperatures.<name>).")),
            ("channel", tr("NI channel"), tr("NI analog input, e.g. ai0 (JSON key: channel).")),
            ("warning", tr("Warning threshold (°C)"), tr("Warning temperature (JSON key: warning).")),
            ("critical", tr("Critical threshold (°C)"),
             tr("Critical temperature triggering the power-down (JSON key: critical).")),
            ("requires", tr("Required channels"),
             tr("Sensor considered only if these channels are ON (JSON key: requires).")),
            ("valid_min", tr("Plausible T min (°C)"), tr("Below: sensor in FAULT (JSON key: valid_min).")),
            ("valid_max", tr("Plausible T max (°C)"), tr("Above: sensor in FAULT (JSON key: valid_max).")),
            ("converter", tr("Converter"),
             tr("Voltage→°C conversion; double-click opens the assistant (JSON key: converter).")),
            ("ref_channel", tr("Reference channel"), tr("Channel providing the bridge voltage (JSON key: ref_channel).")),
            ("ref_voltage", tr("Expected ref V (V)"), tr("Expected reference voltage (JSON key: ref_voltage).")),
            ("ref_tol", tr("Ref. tolerance"), tr("Tolerated relative deviation on the reference (JSON key: ref_tol).")),
            ("ai_min", tr("NI input min (V)"), tr("Lower bound of the NI input range (JSON key: ai_min).")),
            ("ai_max", tr("NI input max (V)"), tr("Upper bound of the NI input range (JSON key: ai_max).")),
        ]

    def _rl_cols(self):
        tr = self.tr
        return [
            ("name", tr("Instrument"), tr("Relay instrument name (JSON key: instruments.<name>).")),
            ("driver", tr("Driver"), tr("Relay driver (only MOCK-RELAY exists for now).")),
            ("outputs", tr("Outputs"), tr("Output labels, comma-separated (e.g. K1, K2).")),
            ("safe_on", tr("Closed at shutdown"),
             tr("Outputs left CLOSED in the safe state (the others are open), "
                "comma-separated. Empty = all open.")),
        ]

    @staticmethod
    def _make_table(cols):
        """Crée une QTableWidget dont les en-têtes portent le libellé français et
        un tooltip (rappelant la clé JSON). Retourne (table, liste des clés)."""
        table = QtWidgets.QTableWidget(0, len(cols))
        for i, (key, label, tip) in enumerate(cols):
            item = QtWidgets.QTableWidgetItem(label)
            item.setToolTip(tip)
            table.setHorizontalHeaderItem(i, item)
        header = table.horizontalHeader()
        # Chaque colonne s'ajuste à son contenu ET à son en-tête (plus de libellés
        # tronqués comme « Seuil critique (°C ») ; l'utilisateur peut ensuite
        # redimensionner à la main. Un défilement horizontal apparaît si besoin.
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(len(cols) - 1, QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(True)
        return table, [c[0] for c in cols]

    def _build_config_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        self.cfg_header_label = QtWidgets.QLabel(self.tr(
            "Interactive configuration editing. Renamed or deleted "
            "channels/groups/sensors are checked on “Apply”."))
        v.addWidget(self.cfg_header_label)

        sub = QtWidgets.QTabWidget()
        v.addWidget(sub, 1)

        # --- Sous-onglet Alimentations ---
        sup_page = QtWidgets.QWidget(); sv = QtWidgets.QVBoxLayout(sup_page)
        sv.addWidget(QtWidgets.QLabel(self.tr("VISA address of each supply. "
                                      "“Scan VISA” detects the connected instruments.")))
        self.sup_table, self.sup_cols = self._make_table(self._sup_cols())
        sv.addWidget(self.sup_table)
        sb = QtWidgets.QHBoxLayout()
        for txt, fn in [(self.tr("+ Add"), lambda: self._add_supply()),
                        (self.tr("− Remove"), self._del_supply)]:
            b = QtWidgets.QPushButton(txt); b.clicked.connect(fn); sb.addWidget(b)
        self._btn_scan = QtWidgets.QPushButton(self.tr("Scan VISA…"))
        self._btn_scan.clicked.connect(self._scan)
        sb.addWidget(self._btn_scan)
        self._btn_test = QtWidgets.QPushButton(self.tr("Test the connection…"))
        self._btn_test.clicked.connect(self._test_connection)
        sb.addWidget(self._btn_test)
        sb.addStretch(1)
        sv.addLayout(sb)
        sub.addTab(sup_page, self.tr("Supplies"))

        # --- Sous-onglet Voies ---
        ch_page = QtWidgets.QWidget(); cv = QtWidgets.QVBoxLayout(ch_page)
        cv.addWidget(QtWidgets.QLabel(self.tr("A channel = one physical channel of a supply. "
                                      "“negative” for a rail wired in reverse.")))
        self.ch_table, self.ch_cols = self._make_table(self._ch_cols())
        cv.addWidget(self.ch_table)
        cb = QtWidgets.QHBoxLayout()
        for txt, fn in [(self.tr("+ Add"), lambda: self._add_channel()),
                        (self.tr("− Remove"), self._del_channel)]:
            b = QtWidgets.QPushButton(txt); b.clicked.connect(fn); cb.addWidget(b)
        cb.addStretch(1)
        cv.addLayout(cb)
        sub.addTab(ch_page, self.tr("Channels"))

        # --- Sous-onglet Groupes (voies en série) ---
        gp_page = QtWidgets.QWidget(); gv = QtWidgets.QVBoxLayout(gp_page)
        gv.addWidget(QtWidgets.QLabel(self.tr(
            "Group = channels in SERIES (summed voltage, common current), driven "
            "by its name. Members = comma-separated channels. max=0 → auto.")))
        self.gp_table, self.gp_cols = self._make_table(self._gp_cols())
        gv.addWidget(self.gp_table)
        gb = QtWidgets.QHBoxLayout()
        for txt, fn in [(self.tr("+ Add"), lambda: self._add_group()),
                        (self.tr("− Remove"), self._del_group)]:
            b = QtWidgets.QPushButton(txt); b.clicked.connect(fn); gb.addWidget(b)
        gb.addStretch(1)
        gv.addLayout(gb)
        sub.addTab(gp_page, self.tr("Groups"))

        # --- Sous-onglet Températures ---
        tp_page = QtWidgets.QWidget(); tv = QtWidgets.QVBoxLayout(tp_page)
        tv.addWidget(QtWidgets.QLabel(self.tr(
            "A sensor = one NI channel (ai…). “Converter…” opens the assistant "
            "(type + settings) and applies it directly, no copy-paste.")))
        self.tp_table, self.tp_cols = self._make_table(self._tp_cols())
        self.tp_table.cellDoubleClicked.connect(self._on_temp_dblclick)
        tv.addWidget(self.tp_table)
        tb = QtWidgets.QHBoxLayout()
        for txt, fn in [(self.tr("+ Add"), lambda: self._add_temp()),
                        (self.tr("− Remove"), self._del_temp),
                        (self.tr("Converter…"), self._edit_converter)]:
            b = QtWidgets.QPushButton(txt); b.clicked.connect(fn); tb.addWidget(b)
        tb.addStretch(1)
        tv.addLayout(tb)
        sub.addTab(tp_page, self.tr("Temperatures"))

        # --- Sous-onglet Relais ---
        rl_page = QtWidgets.QWidget(); rv = QtWidgets.QVBoxLayout(rl_page)
        rv.addWidget(QtWidgets.QLabel(self.tr(
            "Relays / actuators: an instrument exposes driveable <b>outputs</b> "
            "(sequence: <code>RELAY &lt;output&gt; ON|OFF</code>). Each output is "
            "brought back to its safe state at shutdown (open by default). No real "
            "hardware model is integrated yet (MOCK-RELAY = simulated relay).")))
        self.rl_table, self.rl_cols = self._make_table(self._rl_cols())
        rv.addWidget(self.rl_table)
        rb = QtWidgets.QHBoxLayout()
        for txt, fn in [(self.tr("+ Add"), lambda: self._add_relay()),
                        (self.tr("− Remove"), self._del_relay)]:
            b = QtWidgets.QPushButton(txt); b.clicked.connect(fn); rb.addWidget(b)
        rb.addStretch(1)
        rv.addLayout(rb)
        sub.addTab(rl_page, self.tr("Relays"))

        # --- Sous-onglet Avancé (JSON complet) ---
        adv_page = QtWidgets.QWidget(); av = QtWidgets.QVBoxLayout(adv_page)
        av.addWidget(QtWidgets.QLabel(self.tr(
            "<b>Full configuration (JSON)</b> — free editing. Synced with the "
            "forms: the active tab is authoritative on save.")))
        self.cfg_json = QtWidgets.QPlainTextEdit()
        self.cfg_json.setFont(QtGui.QFont("Monospace"))
        av.addWidget(self.cfg_json, 1)
        sub.addTab(adv_page, self.tr("Advanced (JSON)"))

        self.cfg_sub = sub
        self._cfg_adv_index = sub.indexOf(adv_page)
        self._cfg_prev_subtab = sub.currentIndex()
        sub.currentChanged.connect(self._on_cfg_subtab_changed)
        self.sup_table.itemChanged.connect(lambda *_: self._refresh_channel_supplies())

        # --- Boutons (partagés) ---
        bb = QtWidgets.QHBoxLayout()
        for txt, fn in [(self.tr("Converter assistant…"), self._assistant),
                        (self.tr("Reload the file"), self._cfg_reload_file),
                        (self.tr("Check"), self._cfg_verify),
                        (self.tr("Save"), self._cfg_save)]:
            b = QtWidgets.QPushButton(txt); b.clicked.connect(fn); bb.addWidget(b)
        self.cfg_apply_btn = QtWidgets.QPushButton(self.tr("✓ Apply (reload hardware)"))
        self.cfg_apply_btn.setStyleSheet(theme.style("button.apply", "font-weight:bold;"))
        self.cfg_apply_btn.clicked.connect(self._cfg_apply)
        bb.addWidget(self.cfg_apply_btn)
        v.addLayout(bb)
        self.cfg_status = QtWidgets.QLabel("")
        v.addWidget(self.cfg_status)

        self._cfg_reload_file()
        self._update_cfg_labels()
        return w

    # --- helpers tableaux ---
    def _supply_names(self) -> List[str]:
        return [self.sup_table.item(i, 0).text().strip()
                for i in range(self.sup_table.rowCount())
                if self.sup_table.item(i, 0) and self.sup_table.item(i, 0).text().strip()]

    def _refresh_channel_supplies(self) -> None:
        """Met à jour la liste déroulante des alims dans chaque voie (préserve le
        choix courant) — appelé quand on ajoute/supprime/renomme une alim."""
        names = self._supply_names()
        for r in range(self.ch_table.rowCount()):
            combo = self.ch_table.cellWidget(r, 1)
            if not isinstance(combo, QtWidgets.QComboBox):
                continue
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear(); combo.addItems(names)
            if cur in names:
                combo.setCurrentText(cur)
            combo.blockSignals(False)

    def _add_supply(self, name="PSU", model="HMP4040",
                    resource="TCPIP0::192.168.0.10::5025::SOCKET"):
        r = self.sup_table.rowCount(); self.sup_table.insertRow(r)
        self.sup_table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
        combo = QtWidgets.QComboBox(); combo.addItems(available_models())
        if model in available_models():
            combo.setCurrentText(model)
        self.sup_table.setCellWidget(r, 1, combo)
        self.sup_table.setItem(r, 2, QtWidgets.QTableWidgetItem(resource))
        self._refresh_channel_supplies()

    def _cell_text(self, table, r, c) -> str:
        it = table.item(r, c)
        return it.text().strip() if it else "?"

    def _confirm_delete(self, kind: str, name: str, extra: str = "") -> bool:
        msg = self.tr("Delete {} “{}”?").format(kind, name)
        if extra:
            msg += "\n" + extra
        return QtWidgets.QMessageBox.question(
            self, self.tr("Confirm deletion"), msg) == QtWidgets.QMessageBox.Yes

    def _del_supply(self):
        r = self.sup_table.currentRow()
        if r < 0:
            return
        if not self._confirm_delete(self.tr("the supply"), self._cell_text(self.sup_table, r, 0),
                                    self.tr("Channels referencing it will need to be reassigned.")):
            return
        self.sup_table.removeRow(r)
        self._refresh_channel_supplies()

    def _add_channel(self, label="V?", supply="", channel=1, negative=False,
                     dv=0.0, di=0.1, mv=32.0, mi=10.0):
        r = self.ch_table.rowCount(); self.ch_table.insertRow(r)
        self.ch_table.setItem(r, 0, QtWidgets.QTableWidgetItem(label))
        combo = QtWidgets.QComboBox()
        names = [self.sup_table.item(i, 0).text() for i in range(self.sup_table.rowCount())]
        combo.addItems(names or [supply])
        if supply in names:
            combo.setCurrentText(supply)
        self.ch_table.setCellWidget(r, 1, combo)
        spin = QtWidgets.QSpinBox(); spin.setRange(1, 4); spin.setValue(int(channel))
        self.ch_table.setCellWidget(r, 2, spin)
        chk = QtWidgets.QCheckBox(); chk.setChecked(bool(negative))
        self.ch_table.setCellWidget(r, 3, chk)
        for col, val in zip((4, 5, 6, 7), (dv, di, mv, mi)):
            self.ch_table.setItem(r, col, QtWidgets.QTableWidgetItem(str(val)))

    def _del_channel(self):
        r = self.ch_table.currentRow()
        if r < 0:
            return
        if not self._confirm_delete(
                self.tr("the channel"), self._cell_text(self.ch_table, r, 0),
                self.tr("References in groups/sensors/sequences will need to be fixed manually.")):
            return
        self.ch_table.removeRow(r)

    # --- helpers groupes ---
    def _add_group(self, name="G", members="", split="equal", mv=0.0, mi=0.0):
        r = self.gp_table.rowCount(); self.gp_table.insertRow(r)
        self.gp_table.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
        self.gp_table.setItem(r, 1, QtWidgets.QTableWidgetItem(members))
        combo = QtWidgets.QComboBox()
        combo.addItem(self.tr("balanced"), "equal")
        combo.addItem(self.tr("fill"), "fill")
        idx = combo.findData(split if split in ("equal", "fill") else "equal")
        combo.setCurrentIndex(max(0, idx))
        self.gp_table.setCellWidget(r, 2, combo)
        self.gp_table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(mv)))
        self.gp_table.setItem(r, 4, QtWidgets.QTableWidgetItem(str(mi)))

    def _del_group(self, *_):
        r = self.gp_table.currentRow()
        if r < 0:
            return
        if not self._confirm_delete(self.tr("the group"), self._cell_text(self.gp_table, r, 0)):
            return
        self.gp_table.removeRow(r)

    def _collect_groups(self) -> dict:
        out = {}
        for r in range(self.gp_table.rowCount()):
            def cell(c):
                it = self.gp_table.item(r, c)
                return it.text().strip() if it else ""
            name = cell(0)
            if not name:
                continue
            out[name] = {
                "members": [x.strip() for x in cell(1).split(",") if x.strip()],
                "mode": "series",
                "split": self.gp_table.cellWidget(r, 2).currentData(),
                "max_voltage": float(cell(3) or 0.0),
                "max_current": float(cell(4) or 0.0),
            }
        return out

    def _add_relay(self, name="RLY", driver="MOCK-RELAY", outputs="", safe_on=""):
        r = self.rl_table.rowCount(); self.rl_table.insertRow(r)
        for c, val in enumerate([name, driver, outputs, safe_on]):
            self.rl_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(val)))

    def _del_relay(self, *_):
        r = self.rl_table.currentRow()
        if r < 0:
            return
        if not self._confirm_delete(self.tr("the relay"), self._cell_text(self.rl_table, r, 0)):
            return
        self.rl_table.removeRow(r)

    def _collect_relays(self) -> dict:
        """Instruments relais saisis, au format ``instruments`` (driver + outputs)."""
        out = {}
        for r in range(self.rl_table.rowCount()):
            def cell(c):
                it = self.rl_table.item(r, c)
                return it.text().strip() if it else ""
            name = cell(0)
            outs = [x.strip() for x in cell(2).split(",") if x.strip()]
            safe_list = [x.strip() for x in cell(3).split(",") if x.strip()]
            # Une sortie « fermée à l'arrêt » est nécessairement une sortie : si elle
            # manque dans la colonne Sorties, on l'y ajoute (au lieu de l'ignorer en
            # silence, ce qui perdrait l'intention de l'utilisateur).
            for s in safe_list:
                if s not in outs:
                    outs.append(s)
            if not name or not outs:
                continue
            safe = set(safe_list)
            out[name] = {
                "driver": cell(1) or "MOCK-RELAY",
                "outputs": {o: {"safe_state": o in safe} for o in outs},
            }
        return out

    def _collect_supplies(self) -> dict:
        out = {}
        for r in range(self.sup_table.rowCount()):
            name = self.sup_table.item(r, 0).text().strip()
            combo = self.sup_table.cellWidget(r, 1)
            model = combo.currentText() if isinstance(combo, QtWidgets.QComboBox) else "HMP4040"
            res_item = self.sup_table.item(r, 2)
            res = res_item.text().strip() if res_item else ""
            if name:
                out[name] = {"model": model, "resource": res}
        return out

    def _collect_channels(self) -> dict:
        out = {}
        for r in range(self.ch_table.rowCount()):
            label = self.ch_table.item(r, 0).text().strip()
            if not label:
                continue
            d = {
                "supply": self.ch_table.cellWidget(r, 1).currentText(),
                "channel": self.ch_table.cellWidget(r, 2).value(),
                "default_voltage": float(self.ch_table.item(r, 4).text()),
                "default_current": float(self.ch_table.item(r, 5).text()),
                "max_voltage": float(self.ch_table.item(r, 6).text()),
                "max_current": float(self.ch_table.item(r, 7).text()),
            }
            if self.ch_table.cellWidget(r, 3).isChecked():
                d["negative"] = True
            out[label] = d
        return out

    # --- helpers températures ---
    @staticmethod
    def _conv_summary(d: dict) -> str:
        t = d.get("type", "?")
        if t == "table":
            return f"table ({len(d.get('points', []))} pts)"
        return t

    def _add_temp(self, name="T?", channel="ai0", warning=70.0, critical=85.0,
                  requires="", vmin="", vmax="", converter=None,
                  ref_channel="", ref_voltage="", ref_tol="", ai_min=-10.0, ai_max=10.0):
        converter = converter or {"type": "identity"}
        r = self.tp_table.rowCount(); self.tp_table.insertRow(r)
        for col, val in enumerate([name, channel, warning, critical, requires, vmin, vmax]):
            self.tp_table.setItem(r, col, QtWidgets.QTableWidgetItem(str(val)))
        conv_item = QtWidgets.QTableWidgetItem(self._conv_summary(converter))
        conv_item.setFlags(conv_item.flags() & ~QtCore.Qt.ItemIsEditable)
        conv_item.setData(QtCore.Qt.UserRole, json.dumps(converter))
        self.tp_table.setItem(r, 7, conv_item)
        self.tp_table.setItem(r, 8, QtWidgets.QTableWidgetItem(str(ref_channel)))
        self.tp_table.setItem(r, 9, QtWidgets.QTableWidgetItem(str(ref_voltage)))
        self.tp_table.setItem(r, 10, QtWidgets.QTableWidgetItem(str(ref_tol)))
        self.tp_table.setItem(r, 11, QtWidgets.QTableWidgetItem(str(ai_min)))
        self.tp_table.setItem(r, 12, QtWidgets.QTableWidgetItem(str(ai_max)))

    def _del_temp(self, *_):
        r = self.tp_table.currentRow()
        if r < 0:
            return
        if not self._confirm_delete(self.tr("the sensor"), self._cell_text(self.tp_table, r, 0)):
            return
        self.tp_table.removeRow(r)

    def _on_temp_dblclick(self, row: int, col: int) -> None:
        if col == 7:  # colonne « convertisseur »
            self._edit_converter()

    def _edit_converter(self, *_):
        r = self.tp_table.currentRow()
        if r < 0:
            QtWidgets.QMessageBox.information(self, self.tr("Converter"),
                                              self.tr("First select a sensor in the table."))
            return
        item = self.tp_table.item(r, 7)
        try:
            current = json.loads(item.data(QtCore.Qt.UserRole)) if item and \
                item.data(QtCore.Qt.UserRole) else {"type": "identity"}
        except Exception:
            current = {"type": "identity"}
        dlg = ConverterAssistant(self)
        dlg.set_converter(current)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        try:
            conv = dlg.converter_dict()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Converter"), self.tr("Invalid parameters: {}").format(exc))
            return
        if item is None:
            item = QtWidgets.QTableWidgetItem()
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.tp_table.setItem(r, 7, item)
        item.setText(self._conv_summary(conv))
        item.setData(QtCore.Qt.UserRole, json.dumps(conv))

    def _collect_temps(self) -> dict:
        out = {}
        for r in range(self.tp_table.rowCount()):
            def cell(c):
                it = self.tp_table.item(r, c)
                return it.text().strip() if it else ""
            name = cell(0)
            if not name:
                continue
            d = {"channel": cell(1), "warning": float(cell(2)), "critical": float(cell(3))}
            if cell(4):
                d["requires"] = [x.strip() for x in cell(4).split(",") if x.strip()]
            if cell(5):
                d["valid_min"] = float(cell(5))
            if cell(6):
                d["valid_max"] = float(cell(6))
            conv_item = self.tp_table.item(r, 7)
            try:
                d["converter"] = json.loads(conv_item.data(QtCore.Qt.UserRole)) if conv_item and \
                    conv_item.data(QtCore.Qt.UserRole) else {"type": "identity"}
            except Exception:
                d["converter"] = {"type": "identity"}
            if cell(8):
                d["ref_channel"] = cell(8)
                if cell(9):
                    d["ref_voltage"] = float(cell(9))
                d["ref_tol"] = float(cell(10)) if cell(10) else 0.05
            if cell(11):
                d["ai_min"] = float(cell(11))
            if cell(12):
                d["ai_max"] = float(cell(12))
            out[name] = d
        return out

    def _fill_forms_from_raw(self, raw: dict) -> None:
        # Sources : depuis 'supplies' (legacy) ET les entrées source de 'instruments'
        # (une config peut être écrite dans l'un ou l'autre format).
        self.sup_table.setRowCount(0)
        seen = set()
        for name, s in (raw.get("supplies") or {}).items():
            self._add_supply(name, s.get("model", "HMP4040"), s.get("resource", ""))
            seen.add(name)
        for name, e in (raw.get("instruments") or {}).items():
            if name in seen or driver_role(str((e or {}).get("driver", ""))) != "source":
                continue
            self._add_supply(name, e.get("driver", "HMP4040"), e.get("resource", ""))
            seen.add(name)
        self.ch_table.setRowCount(0)
        for label, c in raw.get("channels", {}).items():
            self._add_channel(label, c.get("supply", ""), c.get("channel", 1),
                              bool(c.get("negative") or float(c.get("polarity", 1)) < 0),
                              c.get("default_voltage", 0.0), c.get("default_current", 0.1),
                              c.get("max_voltage", 32.0), c.get("max_current", 10.0))
        self.gp_table.setRowCount(0)
        for name, g in raw.get("groups", {}).items():
            self._add_group(name, ", ".join(g.get("members", [])),
                            g.get("split", "equal"),
                            g.get("max_voltage", 0.0), g.get("max_current", 0.0))
        self.tp_table.setRowCount(0)
        for name, t in raw.get("temperatures", {}).items():
            req = t.get("requires", [])
            if isinstance(req, str):
                req = [req]
            self._add_temp(name, t.get("channel", "ai0"), t.get("warning", 70.0),
                           t.get("critical", 85.0), ",".join(req),
                           "" if t.get("valid_min") is None else t.get("valid_min"),
                           "" if t.get("valid_max") is None else t.get("valid_max"),
                           t.get("converter", {"type": "identity"}),
                           t.get("ref_channel", "") or "",
                           "" if t.get("ref_voltage") is None else t.get("ref_voltage"),
                           "" if t.get("ref_channel") is None else t.get("ref_tol", 0.05),
                           t.get("ai_min", -10.0), t.get("ai_max", 10.0))
        self.rl_table.setRowCount(0)
        for name, e in (raw.get("instruments") or {}).items():
            if driver_role(str((e or {}).get("driver", ""))) != "actuator":
                continue
            outs = (e or {}).get("outputs", [])
            if isinstance(outs, dict):
                labels = list(outs.keys())
                safe = [l for l, m in outs.items() if (m or {}).get("safe_state")]
            else:
                labels, safe = list(outs), []
            self._add_relay(name, e.get("driver", "MOCK-RELAY"),
                            ", ".join(labels), ", ".join(safe))
        self._refresh_channel_supplies()

    def _cfg_reload_file(self) -> None:
        try:
            raw = json.loads(Path(self._cfg_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # Fichier supprimé ou corrompu depuis le chargement : ne pas planter,
            # laisser les formulaires en l'état et signaler l'échec.
            self.cfg_status.setText(
                self.tr("Cannot reload {}: {}").format(Path(self._cfg_path).name, exc))
            self.cfg_status.setStyleSheet(theme.style("text.error"))
            return
        self._fill_forms_from_raw(raw)
        self.cfg_json.setPlainText(json.dumps(raw, indent=2, ensure_ascii=False))
        self.cfg_status.setText(self.tr("Configuration loaded from {}.").format(Path(self._cfg_path).name))
        self.cfg_status.setStyleSheet(theme.style("text.muted"))

    def _forms_to_dict(self) -> dict:
        return {
            "supplies": self._collect_supplies(),
            "channels": self._collect_channels(),
            "groups": self._collect_groups(),
            "temperatures": self._collect_temps(),
        }

    def _full_config_dict(self) -> dict:
        """JSON complet courant, avec les sections des formulaires par-dessus."""
        raw = json.loads(self.cfg_json.toPlainText() or "{}")
        raw.update(self._forms_to_dict())
        # Relais : on fusionne dans 'instruments' SANS toucher aux autres instruments
        # (sources/température) éventuellement déclarés en JSON. Les sources restent en
        # 'supplies' : AppConfig fusionne les deux (cf. config.AppConfig.__post_init__).
        relays = self._collect_relays()
        # On conserve les instruments non-source et non-actionneur (ex. température),
        # on retire les sources (émises via 'supplies' par le formulaire, pour éviter
        # tout doublon/masquage) et on (re)pose les relais du formulaire.
        instr = {k: v for k, v in (raw.get("instruments") or {}).items()
                 if driver_role(str((v or {}).get("driver", ""))) not in ("actuator", "source")}
        instr.update(relays)
        if instr:
            raw["instruments"] = instr
        elif "instruments" in raw:
            del raw["instruments"]
        return raw

    def _sync_forms_to_json(self) -> None:
        self.cfg_json.setPlainText(
            json.dumps(self._full_config_dict(), indent=2, ensure_ascii=False))

    def _sync_json_to_forms(self) -> None:
        self._fill_forms_from_raw(json.loads(self.cfg_json.toPlainText() or "{}"))

    def _on_cfg_subtab_changed(self, idx: int) -> None:
        prev, self._cfg_prev_subtab = self._cfg_prev_subtab, idx
        try:
            if idx == self._cfg_adv_index:
                self._sync_forms_to_json()   # on ouvre le JSON : il reflète les formulaires
            elif prev == self._cfg_adv_index:
                self._sync_json_to_forms()   # on quitte le JSON : les formulaires le reflètent
        except Exception:
            pass  # JSON en cours d'édition (invalide) : ne pas casser la navigation
        self._refresh_channel_supplies()

    def _collect_config(self) -> dict:
        # L'onglet ACTIF fait foi : on y aligne l'autre vue, puis le JSON complet
        # est la source unique de l'enregistrement.
        if self.cfg_sub.currentIndex() == self._cfg_adv_index:
            self._sync_json_to_forms()
        else:
            self._sync_forms_to_json()
        return json.loads(self.cfg_json.toPlainText() or "{}")

    def _cfg_validate(self):
        try:
            raw = self._collect_config()
        except Exception as exc:
            return None, self.tr("✗ Invalid form/JSON: {}").format(exc)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump(raw, f); tmp = f.name
        try:
            load_config(tmp)
            return raw, self.tr("✓ Valid configuration.")
        except Exception as exc:
            return None, f"✗ {exc}"
        finally:
            try:
                Path(tmp).unlink()
            except OSError:
                pass

    def _cfg_verify(self) -> bool:
        raw, msg = self._cfg_validate()
        self.cfg_status.setText(msg)
        self.cfg_status.setStyleSheet(theme.style("text.ok" if raw else "text.error"))
        return raw is not None

    def _write_config_to(self, path) -> bool:
        """Valide l'état courant de l'onglet et l'écrit dans ``path``. Aucun
        écrit partiel si l'état est invalide (message + abandon)."""
        raw, msg = self._cfg_validate()
        if raw is None:
            self.cfg_status.setText(msg); self.cfg_status.setStyleSheet(theme.style("text.error"))
            QtWidgets.QMessageBox.critical(self, self.tr("Invalid configuration"), msg)
            return False
        Path(path).write_text(json.dumps(raw, indent=2, ensure_ascii=False),
                              encoding="utf-8")
        return True

    def _cfg_save(self) -> bool:
        if not self._write_config_to(self._cfg_path):
            return False
        self.cfg_status.setText(self.tr("✓ Saved to {}.").format(Path(self._cfg_path).name))
        self.cfg_status.setStyleSheet(theme.style("text.ok"))
        return True

    def _cfg_apply(self) -> None:
        if self.runner.is_running:
            QtWidgets.QMessageBox.information(self, self.tr("Configuration"),
                                              self.tr("Stop the sequence before applying."))
            return
        if not self._cfg_save():
            return
        if QtWidgets.QMessageBox.question(
                self, self.tr("Apply"), self.tr("The hardware will be switched off then reloaded.\nContinue?")
        ) != QtWidgets.QMessageBox.Yes:
            return
        self._reload_controller()

    def _reload_controller(self, path=None) -> None:
        target = Path(path) if path is not None else self._cfg_path
        try:
            new_cfg = load_config(target)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, self.tr("Invalid configuration"), str(exc))
            return
        try:
            self.runner.force_stop(); self.ctrl.close()
        except Exception:
            pass
        self.ctrl = Controller(new_cfg)
        self.ctrl.enable_file_logging()
        self.runner = self.ctrl.runner
        self.runner.on_line = self._on_seq_line
        # La fin de séquence passe par le contrôleur (qui marque l'issue de
        # l'essai via son propre runner.on_finish) avant de nous être relayée —
        # comme au démarrage. Poser runner.on_finish ici écraserait ce relais et
        # laisserait l'issue de l'essai non marquée (« Terminé » à tort).
        self.ctrl.on_seq_finish = self._on_seq_finish
        self._actions = []
        self._seq_run_line = 0
        # Bascule sur le fichier chargé (modèle document).
        self._cfg_path = target.resolve()
        self._settings.setValue("last_profile", str(self._cfg_path))
        self._rebuild_tabs()
        self.tabs.setCurrentIndex(0)
        self._update_cfg_labels()
        self.ctrl.log(self.tr("Configuration applied: {}").format(self._cfg_path))
        # Connexion déportée (ne fige pas l'IHM sur un timeout VISA).
        self._connect_async()

    def _assistant(self) -> None:
        dlg = ConverterAssistant(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            try:
                block = json.dumps(dlg.converter_dict(), ensure_ascii=False)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, self.tr("Assistant"), self.tr("Invalid parameters: {}").format(exc))
                return
            QtWidgets.QApplication.clipboard().setText(block)
            QtWidgets.QMessageBox.information(
                self, self.tr("Converter assistant"),
                self.tr("'converter' block copied to the clipboard:\n\n{}\n\n"
                        "Paste it into a sensor of the 'temperatures' section (JSON).").format(block))

    def _test_connection(self) -> None:
        if self.ctrl.cfg.simulate:
            QtWidgets.QMessageBox.information(
                self, self.tr("Connection test"), self.tr("SIMULATION mode: nothing to test."))
            return
        r = self.sup_table.currentRow()
        if r < 0:
            QtWidgets.QMessageBox.information(self, self.tr("Connection test"),
                                              self.tr("Select a supply in the table."))
            return
        name = self.sup_table.item(r, 0).text().strip()
        combo = self.sup_table.cellWidget(r, 1)
        model = combo.currentText() if isinstance(combo, QtWidgets.QComboBox) else "HMP4040"
        res_item = self.sup_table.item(r, 2)
        resource = res_item.text().strip() if res_item else ""
        from ..psu import create_psu

        def work():
            # Ne touche AUCUN widget : renvoie juste les infos de l'instrument.
            psu = create_psu(model=model, resource=resource, simulate=False,
                             visa_backend=self.ctrl.cfg.visa_backend, log=self.ctrl.log)
            psu.connect()
            idn = getattr(psu, "idn", "")
            n = psu.n_channels
            psu.close()
            return idn, n

        def done(result):
            idn, n = result
            QtWidgets.QMessageBox.information(
                self, self.tr("Connection test"),
                self.tr("{}: OK ✓\n\nModel: {} ({} channels)\nIDN: {}").format(name, model, n, idn))

        def failed(msg):
            QtWidgets.QMessageBox.critical(self, self.tr("Connection test"), self.tr("{}: FAILURE\n\n{}").format(name, msg))

        self._start_hw_task(work, done, failed, busy_widgets=(self._btn_test,), cursor=True)

    def _scan(self) -> None:
        if self.ctrl.cfg.simulate:
            QtWidgets.QMessageBox.information(
                self, self.tr("VISA scan"), self.tr("Unavailable in SIMULATION mode (simulate: true)."))
            return

        def work():
            return scan_instruments(model_filter="HMP", visa_backend=self.ctrl.cfg.visa_backend)

        def done(found):
            if not found:
                QtWidgets.QMessageBox.information(self, self.tr("VISA scan"), self.tr("No instrument found."))
                return
            items = ["{}    [{}]".format(d['resource'], d['idn'] or self.tr('no IDN response')) for d in found]
            choice, ok = QtWidgets.QInputDialog.getItem(
                self, self.tr("Detected instruments"),
                self.tr("Assign the resource to the selected channel:"), items, 0, False)
            if ok and choice:
                res = found[items.index(choice)]["resource"]
                r = self.sup_table.currentRow()
                if r < 0:
                    self._add_supply("PSU", "HMP4040", res)
                else:
                    self.sup_table.setItem(r, 2, QtWidgets.QTableWidgetItem(res))

        def failed(msg):
            QtWidgets.QMessageBox.critical(self, self.tr("VISA scan"), msg)

        self._start_hw_task(work, done, failed, busy_widgets=(self._btn_scan,), cursor=True)
