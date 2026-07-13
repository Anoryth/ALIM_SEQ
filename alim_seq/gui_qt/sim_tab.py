"""Onglet Simulation : réglage **à chaud** des charges, du modèle thermique et des
couplages grille→drain (mode simulation uniquement). Greffé via :class:`SimMixin`.

But : permettre à l'utilisateur de reproduire fidèlement le comportement attendu de
son montage sans matériel, en voyant l'effet immédiatement (onglet Contrôle). Les
réglages mettent à jour la section ``simulation`` de la configuration en mémoire
(donc conservés au travers d'un reconnect).
"""

from __future__ import annotations

from PySide6 import QtWidgets

from . import theme
from .widgets import NoScrollDoubleSpinBox


class SimMixin:
    """Onglet Simulation, greffé sur :class:`AlimSeqQtGUI`. Présent uniquement en
    mode simulation (voir ``_rebuild_tabs``)."""

    def _build_sim_tab(self) -> QtWidgets.QWidget:
        scroll = QtWidgets.QScrollArea(); scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget(); scroll.setWidget(inner)
        v = QtWidgets.QVBoxLayout(inner)
        params = self.ctrl.sim_params()

        intro = QtWidgets.QLabel(
            "Réglages du <b>mode simulation</b> uniquement, appliqués <b>en direct</b> : "
            "l'effet est visible immédiatement dans l'onglet <i>Contrôle</i> (courants, "
            "montée en température). Ils mettent à jour la section <code>simulation</code> "
            "de la configuration en mémoire.")
        intro.setWordWrap(True)
        intro.setStyleSheet(theme.style("text.muted"))
        v.addWidget(intro)

        # --- Charges résistives par voie ---
        lbox = QtWidgets.QGroupBox("Charges résistives par voie")
        lg = QtWidgets.QGridLayout(lbox)
        lg.addWidget(QtWidgets.QLabel("Une charge R fixe la relation I = V/R "
                                      "(passage en limitation de courant si V/R dépasse "
                                      "la limite)."), 0, 0, 1, 2)
        self._sim_load_spins = {}
        for r, (label, ohms) in enumerate(params["loads"].items(), start=1):
            lg.addWidget(QtWidgets.QLabel(label), r, 0)
            sp = NoScrollDoubleSpinBox()
            sp.setRange(0.0, 1e6); sp.setDecimals(2); sp.setSingleStep(1.0)
            sp.setSuffix(" Ω"); sp.setValue(float(ohms))
            sp.setKeyboardTracking(False); sp.setMaximumWidth(150)
            sp.valueChanged.connect(lambda val, l=label: self.ctrl.sim_set_load(l, val))
            lg.addWidget(sp, r, 1)
            self._sim_load_spins[label] = sp
        lg.setColumnStretch(2, 1)
        v.addWidget(lbox)

        # --- Modèle thermique ---
        tbox = QtWidgets.QGroupBox("Modèle thermique (montée en température simulée)")
        tg = QtWidgets.QGridLayout(tbox)
        th = params["thermal"]
        specs = [
            ("ambient_c", "Ambiante", " °C", 2, -50.0, 200.0, 1.0,
             "Température au repos (puissance nulle)."),
            ("thermal_gain_c_per_w", "Gain", " °C/W", 3, 0.0, 1000.0, 0.5,
             "Élévation par watt dissipé : cible = ambiante + gain × puissance."),
            ("thermal_tau_s", "Constante de temps τ", " s", 2, 0.1, 3600.0, 0.5,
             "Temps de réponse thermique (réponse du 1er ordre vers la cible)."),
            ("noise_c", "Bruit de mesure", " °C", 3, 0.0, 50.0, 0.05,
             "Amplitude du bruit ajouté à chaque lecture."),
        ]
        self._sim_thermal_spins = {}
        for r, (key, name, suf, dec, lo, hi, step, tip) in enumerate(specs):
            lab = QtWidgets.QLabel(name); lab.setToolTip(tip)
            tg.addWidget(lab, r, 0)
            sp = NoScrollDoubleSpinBox()
            sp.setRange(lo, hi); sp.setDecimals(dec); sp.setSingleStep(step)
            sp.setSuffix(suf); sp.setValue(float(th[key]))
            sp.setKeyboardTracking(False); sp.setMaximumWidth(150); sp.setToolTip(tip)
            sp.valueChanged.connect(lambda val, k=key: self.ctrl.sim_set_thermal(**{k: val}))
            tg.addWidget(sp, r, 1)
            self._sim_thermal_spins[key] = sp
        tg.setColumnStretch(2, 1)
        v.addWidget(tbox)

        # --- Couplages entre voies (grille → drain) — toujours présent, éditable ---
        cbox = QtWidgets.QGroupBox("Couplages entre voies (grille → drain)")
        cv = QtWidgets.QVBoxLayout(cbox)
        desc = QtWidgets.QLabel(
            "Modélise un transistor : la tension d'une voie <b>grille</b> pilote le "
            "courant tiré sur une ou plusieurs voies <b>drain</b> "
            "(Id = gm·(Vg − vth), borné à imax) — utile pour tester l'asservissement "
            "(SERVO). Sans couplage, chaque voie se comporte comme une simple charge "
            "résistive (section ci-dessus).")
        desc.setWordWrap(True)
        cv.addWidget(desc)
        self._sim_coupling_table = QtWidgets.QTableWidget(0, 5)
        self._sim_coupling_table.setHorizontalHeaderLabels(
            ["Grille", "Drains (voies/groupes, séparés par « , »)",
             "gm (A/V)", "vth (V)", "imax (A)"])
        self._sim_coupling_table.horizontalHeader().setStretchLastSection(True)
        self._sim_coupling_table.setColumnWidth(1, 240)
        self._sim_coupling_table.verticalHeader().setVisible(False)
        cv.addWidget(self._sim_coupling_table)
        cbtn = QtWidgets.QHBoxLayout()
        addb = QtWidgets.QPushButton("+ Ajouter un couplage")
        addb.clicked.connect(lambda: self._sim_add_coupling_row())
        delb = QtWidgets.QPushButton("− Supprimer")
        delb.clicked.connect(self._sim_del_coupling)
        cbtn.addWidget(addb); cbtn.addWidget(delb); cbtn.addStretch(1)
        cv.addLayout(cbtn)
        v.addWidget(cbox)
        for cpl in params["couplings"]:
            self._sim_add_coupling_row(cpl)

        v.addStretch(1)
        return scroll

    def _sim_add_coupling_row(self, cpl: dict | None = None) -> None:
        """Ajoute une ligne de couplage (préremplie depuis ``cpl`` si fourni)."""
        cpl = cpl or {}
        t = self._sim_coupling_table
        r = t.rowCount(); t.insertRow(r)
        gate = QtWidgets.QComboBox()
        gate.addItems(list(self.ctrl.cfg.channel_labels))
        idx = gate.findText(str(cpl.get("gate", "")))
        gate.setCurrentIndex(idx if idx >= 0 else 0)
        gate.currentIndexChanged.connect(lambda *_: self._sim_apply_couplings())
        t.setCellWidget(r, 0, gate)
        drains = QtWidgets.QLineEdit(", ".join(map(str, cpl.get("drains", []))))
        drains.setPlaceholderText("ex. D1, D2  ou  DRAIN")
        drains.editingFinished.connect(self._sim_apply_couplings)
        t.setCellWidget(r, 1, drains)
        for col, (key, dec, lo, hi, step, dflt) in enumerate(
                [("gm", 4, 0.0, 10.0, 0.001, 0.005),
                 ("vth", 3, -50.0, 50.0, 0.1, 2.0),
                 ("imax", 4, 0.0, 100.0, 0.001, 0.02)], start=2):
            sp = NoScrollDoubleSpinBox()
            sp.setRange(lo, hi); sp.setDecimals(dec); sp.setSingleStep(step)
            sp.setValue(float(cpl.get(key, dflt))); sp.setKeyboardTracking(False)
            sp.valueChanged.connect(lambda *_: self._sim_apply_couplings())
            t.setCellWidget(r, col, sp)

    def _sim_del_coupling(self) -> None:
        t = self._sim_coupling_table
        r = t.currentRow()
        if r >= 0:
            t.removeRow(r)
            self._sim_apply_couplings()

    def _sim_apply_couplings(self) -> None:
        """Reconstruit la liste des couplages depuis la table et l'applique à chaud.
        Les lignes sans grille ou sans drain sont ignorées (édition en cours)."""
        t = self._sim_coupling_table
        couplings = []
        for r in range(t.rowCount()):
            gate = t.cellWidget(r, 0).currentText().strip()
            drains = [d.strip() for d in t.cellWidget(r, 1).text().split(",") if d.strip()]
            if not gate or not drains:
                continue
            couplings.append({
                "gate": gate, "drains": drains,
                "gm": t.cellWidget(r, 2).value(),
                "vth": t.cellWidget(r, 3).value(),
                "imax": t.cellWidget(r, 4).value(),
            })
        self.ctrl.sim_set_couplings(couplings)
