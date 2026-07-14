"""Fenêtre principale de l'IHM Qt : bannière, onglets, refresh, onglet Contrôle,
menus et point d'entrée ``run()``. Les onglets Éditeur, Configuration et Simulation
sont apportés par des mixins (voir editor.py / config_tab.py / sim_tab.py)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

from PySide6 import QtCore, QtGui, QtWidgets

from .. import __version__, i18n
from ..config import load_config
from ..controller import CRITICAL, FAULT, NA, OK, WARNING, Controller
from ..sequencer import Action, SequenceError, estimate_duration, parse_sequence
from .config_tab import ConfigMixin
from .editor import EditorMixin
from .plot import TempPlotQt
from .sim_tab import SimMixin
from . import theme
from .widgets import ChannelRowQt, RelayRowQt, TempRowQt
from .workers import Task


class AlimSeqQtGUI(EditorMixin, ConfigMixin, SimMixin, QtWidgets.QMainWindow):
    def __init__(self, ctrl: Controller):
        super().__init__()
        self.ctrl = ctrl
        self.runner = ctrl.runner
        # Statut de séquence mis à jour par les callbacks (thread séquenceur) puis
        # lu par le timer (thread GUI) -> pas d'accès widget hors thread GUI.
        self._seq_status = (self.tr("No sequence loaded."), "text.muted")
        self.rows: Dict[str, ChannelRowQt] = {}
        self.temp_rows: Dict[str, TempRowQt] = {}
        self.relay_rows: Dict[str, RelayRowQt] = {}
        self.plot = None
        self._replay_dialogs = []          # fenêtres de relecture d'essai ouvertes
        self._actions: List[Action] = []
        self._plot_paused = False
        self._was_running = False
        self._reset_tripped = False   # état trip mémorisé (style du bouton Réarmer)
        # Suivi de la ligne en cours d'exécution (pour la surligner dans l'éditeur).
        self._seq_run_line = 0
        self._seq_from_editor = False
        # Opérations matérielles (VISA/NI) déportées en threads pour ne jamais
        # figer l'IHM. _hw_busy : une opération matérielle est en cours ;
        # _connecting : (re)connexion en cours (bannière dédiée). On garde les
        # QThread vivants dans _hw_tasks jusqu'à leur signal finished.
        self._hw_busy = False
        self._connecting = False
        self._hw_tasks: List[Task] = []
        # Génération de rapports (workers) : références vivantes + garde anti-double
        # rapport automatique sur déclenchement de sécurité pour un même essai.
        self._report_tasks: List[Task] = []
        self._auto_report_done = False
        self._seq_modified = False   # éditeur : modifications non enregistrées
        # Modèle « document » : le fichier de configuration courant. Vient du
        # chemin d'origine de la config chargée (repli config.json résolu si la
        # config a été construite en code).
        sp = getattr(ctrl.cfg, "source_path", None)
        self._cfg_path = Path(sp) if sp else Path("config.json").resolve()
        self._seq_text = ""          # texte de la séquence courante (archivé à l'essai)
        self.runner.on_line = self._on_seq_line
        # La fin de séquence passe par le contrôleur (qui marque l'issue de l'essai)
        # avant de nous être relayée.
        self.ctrl.on_seq_finish = self._on_seq_finish

        self._settings = QtCore.QSettings("ALIM_SEQ", "ALIM_SEQ")
        self._alarm_enabled = self._settings.value("alarm", True, type=bool)
        # Arrêt d'urgence SANS confirmation par défaut (logique « coup de poing ») ;
        # option pour réactiver le dialogue de confirmation.
        self._confirm_emergency = self._settings.value("confirm_emergency", False, type=bool)
        self._alarm_active = False
        self._alarm_tick = 0
        self.setWindowTitle(self.tr("ALIM_SEQ — Power-supply sequencer  v{}").format(__version__))
        self.resize(1100, 840)
        self._build()
        geo = self._settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._install_shortcuts()
        self._apply_theme(self._settings.value("dark", False, type=bool))
        # Aligne les styles « statiques » déjà construits sur le thème restauré
        # (sinon les widgets bithème resteraient stylés en clair au démarrage sombre).
        self.restyle()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(200)

        self._update_cfg_labels()

        # Connexion au matériel DÉPORTÉE : la fenêtre s'affiche tout de suite, la
        # bannière indique « Connexion… » et un timeout VISA ne fige pas l'IHM.
        # Sauf si l'on rouvre le dernier profil (qui recharge et reconnecte lui-même).
        if not self._try_reopen_last_profile():
            self._connect_async(initial=True)

        # Premier lancement : proposer l'assistant de configuration (une seule fois).
        QtCore.QTimer.singleShot(400, self._maybe_first_launch)

    def _try_reopen_last_profile(self) -> bool:
        """Rouvre le dernier profil utilisé au démarrage si l'option est cochée.
        Un ``--config`` explicite (≠ config.json par défaut) gagne toujours. Ne
        fait jamais échouer le démarrage (log + repli silencieux)."""
        if not self._settings.value("reopen_last_profile", False, type=bool):
            return False
        if self._cfg_path != Path("config.json").resolve():
            return False   # profil explicite passé en --config : il l'emporte
        last = self._settings.value("last_profile", "", type=str)
        if not last:
            return False
        p = Path(last)
        if not p.exists():
            self.ctrl.log(self.tr("Last profile not found, ignored: {}").format(last))
            return False
        try:
            load_config(p)
        except Exception as exc:
            self.ctrl.log(self.tr("Last profile invalid, ignored ({}).").format(exc))
            return False
        self._reload_controller(p)
        return True

    # Callbacks séquenceur (thread runner -> on ne touche QUE des attributs).
    def _on_seq_line(self, ln, raw):
        self._seq_status = (f"En cours — L{ln}: {raw}", "text.info")
        self._seq_run_line = ln

    def _on_seq_finish(self, ok, msg):
        self._seq_status = (msg, "text.ok" if ok else "text.error")
        self._seq_run_line = 0

    def _install_shortcuts(self) -> None:
        self._shortcuts = []
        for seq, fn in [(QtGui.QKeySequence.Save, self._seq_save),
                        (QtGui.QKeySequence.Open, self._seq_open),
                        ("F5", self._seq_verify),
                        ("Ctrl+Return", self._seq_load_and_run),
                        ("Ctrl+Shift+X", self._emergency),
                        ("Ctrl+R", self._toggle_record),
                        ("Ctrl+M", self._add_marker)]:
            sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

    # ------------------------------------------------------------- layout
    def _build(self) -> None:
        self._build_menu()
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)

        self.banner = QtWidgets.QLabel(self.tr("Safety: OK"))
        self.banner.setAlignment(QtCore.Qt.AlignCenter)
        bf = self.banner.font(); bf.setPointSize(bf.pointSize() + 2); bf.setBold(True)
        self.banner.setFont(bf)
        self.banner.setStyleSheet(theme.style("status.ok", "padding:6px;"))
        outer.addWidget(self.banner)

        outer.addWidget(self._build_safety_bar())

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs, 1)
        self._rebuild_tabs()

        # Barre d'état : pastille de connexion + mode + cadence + enregistrement.
        sb = self.statusBar()
        self.sb_conn = QtWidgets.QLabel("●")
        self.sb_cadence = QtWidgets.QLabel("")
        self.sb_power = QtWidgets.QLabel("")
        self.sb_power.setToolTip(self.tr("Total power delivered (sum of channels)"))
        self.sb_rec = QtWidgets.QLabel("")
        self.sb_cfg = QtWidgets.QLabel("")
        self.sb_cfg.setToolTip(self.tr("Current configuration file"))
        sb.addWidget(self.sb_conn)
        sb.addWidget(self.sb_cfg)
        sb.addPermanentWidget(self.sb_power)
        sb.addPermanentWidget(self.sb_cadence)
        sb.addPermanentWidget(self.sb_rec)

        # Journal (avec recherche ; masquable en mode compact).
        box = QtWidgets.QGroupBox(self.tr("Log"))
        self._journal_box = box
        bl = QtWidgets.QVBoxLayout(box)
        srow = QtWidgets.QHBoxLayout()
        self.log_search = QtWidgets.QLineEdit()
        self.log_search.setPlaceholderText(self.tr("Search the log…"))
        self.log_search.returnPressed.connect(self._search_log)
        find_btn = QtWidgets.QPushButton(self.tr("Search")); find_btn.clicked.connect(self._search_log)
        srow.addWidget(self.log_search, 1); srow.addWidget(find_btn)
        bl.addLayout(srow)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)   # borne mémoire sur les essais longs
        self.log.setFixedHeight(150)
        bl.addWidget(self.log)
        outer.addWidget(box)

    def _search_log(self) -> None:
        text = self.log_search.text().strip()
        if not text:
            return
        if not self.log.find(text):                 # repart du début si pas trouvé
            self.log.moveCursor(QtGui.QTextCursor.Start)
            self.log.find(text)

    # ---------------------------------------------- barre de sécurité permanente
    # Padding commun à TOUS les boutons de la barre : ils passent tous par le même
    # moteur de rendu QSS (theme.style) -> métriques homogènes, base d'une barre
    # réellement uniforme. Hauteur commune des boutons de la barre.
    _SAFETY_PAD = "padding:6px 14px;"
    _SAFETY_H = 40

    def _reset_style(self, tripped: bool) -> str:
        """Style du bouton « Réarmer » : orange gras saillant en trip, neutre sinon."""
        if tripped:
            return theme.style("button.rearm_alert", self._SAFETY_PAD + " font-weight:bold;")
        return theme.style("button.neutral", self._SAFETY_PAD)

    def _build_safety_bar(self) -> QtWidgets.QWidget:
        """Barre de commandes vitales, VISIBLE sur tous les onglets (sous la
        bannière, au-dessus des onglets). Un seul jeu de widgets : ces boutons
        ne sont PAS dupliqués dans l'onglet Contrôle."""
        bar = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(bar)
        h.setContentsMargins(6, 2, 6, 2)

        self.btn_emerg = QtWidgets.QPushButton(self.tr("⛔ EMERGENCY STOP"))
        self.btn_emerg.setStyleSheet(theme.style("button.emergency", self._SAFETY_PAD + " font-weight:bold;"))
        self.btn_emerg.setMinimumHeight(self._SAFETY_H)
        self.btn_emerg.setToolTip(
            self.tr("ABRUPT, immediate cut-off of all channels (shortcut Ctrl+Shift+X).\n"
                    "No confirmation by default — see “View → Confirm emergency stop”."))
        self.btn_emerg.clicked.connect(self._emergency)
        h.addWidget(self.btn_emerg, 1)

        self.btn_shutdown_seq = QtWidgets.QPushButton(self.tr("⏹ Shutdown sequence"))
        self.btn_shutdown_seq.setStyleSheet(theme.style("button.shutdown", self._SAFETY_PAD + " font-weight:bold;"))
        self.btn_shutdown_seq.setToolTip(
            self.tr("ORDERLY (soft) power-down: runs the shutdown sequence, or switches "
                    "channels off in reverse order if none is defined"))
        self.btn_shutdown_seq.clicked.connect(lambda: self.ctrl.start_shutdown_sequence(trip=False))
        h.addWidget(self.btn_shutdown_seq)

        self.btn_reset = QtWidgets.QPushButton(self.tr("Rearm"))
        self.btn_reset.setStyleSheet(self._reset_style(False))
        self.btn_reset.setToolTip(self.tr("Release the safety lock after a trip"))
        self.btn_reset.clicked.connect(self._reset)
        h.addWidget(self.btn_reset)

        self.btn_alloff = QtWidgets.QPushButton(self.tr("All OFF"))
        self.btn_alloff.setStyleSheet(theme.style("button.neutral", self._SAFETY_PAD))
        self.btn_alloff.setToolTip(self.tr("Switch off all channels (no ramp, without tripping safety)"))
        self.btn_alloff.clicked.connect(self._all_off)
        h.addWidget(self.btn_alloff)

        # Boutons secondaires (à droite de l'arrêt d'urgence) de taille UNIFORME
        # (même hauteur ET même largeur). L'égalisation de largeur est différée (voir
        # _equalize_safety_buttons) : elle exige des métriques fiables (post-« polish »).
        self._safety_secondary = (self.btn_shutdown_seq, self.btn_reset, self.btn_alloff)
        for b in self._safety_secondary:
            b.setMinimumHeight(self._SAFETY_H)
        QtCore.QTimer.singleShot(0, self._equalize_safety_buttons)

        # Badge de mode PERMANENT (marqueur de sérieux et de sécurité) : impossible
        # de confondre simulation et matériel réel.
        self.mode_badge = QtWidgets.QLabel()
        self.mode_badge.setAlignment(QtCore.Qt.AlignCenter)
        self.mode_badge.setMinimumWidth(140)
        bf = self.mode_badge.font(); bf.setBold(True); self.mode_badge.setFont(bf)
        h.addWidget(self.mode_badge)
        self._update_mode_badge()
        return bar

    def _equalize_safety_buttons(self) -> None:
        """Aligne les boutons secondaires de la barre de sécurité sur une largeur
        commune : celle du texte le plus large mesuré EN GRAS (l'état le plus large,
        p.ex. « Réarmer » saillant en trip) + l'habillage QSS (padding/bordure). On
        mesure via QFontMetrics gras — pas le sizeHint de l'état courant, qui
        sous-estime pour un bouton neutre non gras — pour que la largeur ne bouge ni
        au déclenchement ni après un changement de thème. setMinimumWidth (pas
        setFixedWidth) laisse le layout respirer si la police change."""
        for b in self._safety_secondary:
            b.ensurePolished()
        bold = QtGui.QFont(self.btn_reset.font()); bold.setBold(True)
        fm = QtGui.QFontMetrics(bold)
        text_w = max(fm.horizontalAdvance(b.text()) for b in self._safety_secondary)
        # Habillage (padding QSS + bordure) mesuré sur un bouton déjà stylé en gras :
        # identique pour tous puisqu'ils partagent le même style.
        ref = self.btn_shutdown_seq
        chrome = max(0, ref.sizeHint().width() - fm.horizontalAdvance(ref.text()))
        w = text_w + chrome
        for b in self._safety_secondary:
            b.setMinimumWidth(w)

    def _update_mode_badge(self) -> None:
        if self.ctrl.cfg.simulate:
            self.mode_badge.setText("SIMULATION")
            self.mode_badge.setStyleSheet(
                theme.style("badge.sim", "padding:4px 10px; border-radius:3px;"))
            self.mode_badge.setToolTip(self.tr("No hardware driven — simulated model."))
        else:
            self.mode_badge.setText("MATÉRIEL RÉEL")
            self.mode_badge.setStyleSheet(
                theme.style("badge.real", "padding:4px 10px; border-radius:3px;"))
            self.mode_badge.setToolTip(self.tr("Driving REAL hardware — check the config limits."))

    # ------------------------------------------ tâches matérielles (hors GUI)
    def _set_hw_controls_enabled(self, on: bool) -> None:
        """Active/désactive les commandes qui parlent au matériel pendant une
        (re)connexion — SAUF les commandes vitales (arrêt d'urgence, etc.), qui
        doivent rester cliquables même à moitié connecté."""
        for row in self.rows.values():
            row.set_controls_enabled(on)
        for rrow in self.relay_rows.values():
            rrow.set_controls_enabled(on)
        self.btn_start.setEnabled(on)
        self.btn_reconnect.setEnabled(on)
        if hasattr(self, "cfg_apply_btn"):
            self.cfg_apply_btn.setEnabled(on)

    def _start_hw_task(self, fn, on_done, on_failed=None, *,
                       busy_widgets=(), cursor=False, controls=False) -> bool:
        """Exécute ``fn`` (bloquant, VISA/NI) dans un thread. ``on_done``/``on_failed``
        sont appelés dans le thread GUI. Empêche deux opérations matérielles
        simultanées. Retourne False si une opération est déjà en cours."""
        if self._hw_busy:
            return False
        self._hw_busy = True
        if controls:
            self._set_hw_controls_enabled(False)
        for w in busy_widgets:
            w.setEnabled(False)
        if cursor:
            QtGui.QGuiApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

        task = Task(fn, self)
        self._hw_tasks.append(task)   # garde la référence vivante

        def _cleanup():
            self._hw_busy = False
            if cursor:
                QtGui.QGuiApplication.restoreOverrideCursor()
            for w in busy_widgets:
                w.setEnabled(True)
            if controls:
                self._set_hw_controls_enabled(True)

        def _ok(result):
            _cleanup()
            on_done(result)

        def _ko(msg):
            _cleanup()
            if on_failed is not None:
                on_failed(msg)

        task.done.connect(_ok)
        task.failed.connect(_ko)
        task.finished.connect(lambda: self._hw_tasks.remove(task)
                              if task in self._hw_tasks else None)
        task.start()
        return True

    def _connect_async(self, initial: bool = False) -> None:
        """(Re)connecte le matériel dans un thread. La bannière affiche
        « Connexion… » pendant l'opération (gérée par ``_refresh``)."""
        self._connecting = True
        if not self._start_hw_task(self.ctrl.connect, self._on_connect_done,
                                   self._on_connect_done, controls=True):
            self._connecting = False

    def _on_connect_done(self, result) -> None:
        self._connecting = False
        ok = result is True
        if not ok:
            QtWidgets.QMessageBox.critical(
                self, self.tr("Hardware connection"),
                self.tr("Cannot connect to the hardware:\n\n{}\n\nThe GUI stays in "
                        "disconnected mode. Fix the problem then “Reconnect”.").format(
                            self.ctrl.connect_error))

    # ------------------------------------------------------- menu / thème
    def _build_menu(self) -> None:
        mb = self.menuBar()
        m_file = mb.addMenu(self.tr("&File"))
        m_file.addAction(self.tr("Open a sequence…"), self._menu_open_sequence)
        m_file.addSeparator()
        m_file.addAction(self.tr("Configuration wizard…"), self._menu_config_wizard)
        m_file.addAction(self.tr("Load a configuration…"), self._menu_load_config)
        m_file.addAction(self.tr("Save configuration as…"), self._menu_save_config_as)
        m_file.addSeparator()
        m_file.addAction(self.tr("Reopen a test (replay)…"), self._menu_replay_essai)
        m_file.addAction(self.tr("Compare two tests…"), self._menu_compare_essais)
        m_file.addAction(self.tr("Generate a test report…"), self._menu_generate_report)
        self._act_reopen = m_file.addAction(self.tr("Reopen the last profile at startup"))
        self._act_reopen.setCheckable(True)
        self._act_reopen.setChecked(self._settings.value("reopen_last_profile", False, type=bool))
        self._act_reopen.toggled.connect(
            lambda on: self._settings.setValue("reopen_last_profile", on))
        m_file.addSeparator()
        m_file.addAction(self.tr("Quit"), self.close)

        m_view = mb.addMenu(self.tr("&View"))
        self._act_dark = m_view.addAction(self.tr("Dark theme"))
        self._act_dark.setCheckable(True)
        self._act_dark.setChecked(self._settings.value("dark", False, type=bool))
        self._act_dark.toggled.connect(self._toggle_theme)
        self._act_compact = m_view.addAction(self.tr("Compact mode (hide the log)"))
        self._act_compact.setCheckable(True)
        self._act_compact.toggled.connect(self._toggle_compact)
        self._act_alarm = m_view.addAction(self.tr("Sound alert on critical safety"))
        self._act_alarm.setCheckable(True)
        self._act_alarm.setChecked(self._alarm_enabled)
        self._act_alarm.toggled.connect(self._toggle_alarm)
        self._act_confirm_emerg = m_view.addAction(self.tr("Confirm emergency stop"))
        self._act_confirm_emerg.setCheckable(True)
        self._act_confirm_emerg.setChecked(self._confirm_emergency)
        self._act_confirm_emerg.setToolTip(
            self.tr("If checked, emergency stop asks for confirmation (otherwise immediate cut-off)."))
        self._act_confirm_emerg.toggled.connect(self._toggle_confirm_emergency)
        self._act_auto_report = m_view.addAction(self.tr("Generate the report at end of test"))
        self._act_auto_report.setCheckable(True)
        self._act_auto_report.setChecked(
            self._settings.value("auto_report", True, type=bool))
        self._act_auto_report.setToolTip(
            self.tr("At end of recording, prompt for the conclusion then generate the "
                    "PDF report. The report is ALWAYS generated automatically on a safety "
                    "trip."))
        self._act_auto_report.toggled.connect(
            lambda on: self._settings.setValue("auto_report", on))

        m_view.addSeparator()
        m_lang = m_view.addMenu(self.tr("Language"))
        self._lang_group = QtGui.QActionGroup(self)
        self._lang_group.setExclusive(True)
        current = self._settings.value("ui/language", "", type=str)
        for code, label in SUPPORTED_LANGUAGES.items():
            act = m_lang.addAction(label)
            act.setCheckable(True)
            act.setChecked(code == current)
            act.triggered.connect(lambda _checked=False, c=code: self._set_language(c))
            self._lang_group.addAction(act)

        m_help = mb.addMenu(self.tr("&Help"))
        act_manual = m_help.addAction(self.tr("User manual"), self._show_manual)
        act_manual.setShortcut("F1")
        m_help.addAction(self.tr("Keyboard shortcuts"), self._show_shortcuts)
        m_help.addAction(self.tr("Sequence command reference"), self._show_seq_reference)
        m_help.addAction(self.tr("Where are my files?"), self._menu_open_essais_dir)
        m_help.addSeparator()
        m_help.addAction(self.tr("About"), self._about)

    def _apply_theme(self, dark: bool) -> None:
        theme.apply_theme(dark)

    def _toggle_theme(self, dark: bool) -> None:
        self._settings.setValue("dark", dark)
        self._apply_theme(dark)
        self.restyle()

    def _set_language(self, code: str) -> None:
        """Persist the chosen UI language and offer to restart to apply it.

        The GUI is built imperatively (no retranslateUi), so a restart is the
        robust way to re-render every string in the new language."""
        if code == self._settings.value("ui/language", "", type=str):
            return
        self._settings.setValue("ui/language", code)
        ans = QtWidgets.QMessageBox.question(
            self, self.tr("Language"),
            self.tr("The language change will take effect after restarting "
                    "ALIM_SEQ.\n\nQuit now?"),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No)
        if ans == QtWidgets.QMessageBox.Yes:
            self.close()

    def restyle(self) -> None:
        """Ré-applique tous les styles « statiques » (posés une seule fois à la
        construction) au thème courant, et invalide les états mémorisés des voies.
        Les styles « dynamiques » (bannière, températures, pending, statuts) se
        recalculent d'eux-mêmes au tick suivant via theme.style()."""
        self.btn_emerg.setStyleSheet(theme.style("button.emergency", self._SAFETY_PAD + " font-weight:bold;"))
        self.btn_shutdown_seq.setStyleSheet(theme.style("button.shutdown", self._SAFETY_PAD + " font-weight:bold;"))
        self.btn_reset.setStyleSheet(self._reset_style(bool(getattr(self, "_reset_tripped", False))))
        self.btn_alloff.setStyleSheet(theme.style("button.neutral", self._SAFETY_PAD))
        self.btn_start.setStyleSheet(theme.style("button.start", "font-weight:bold;"))
        self._equalize_safety_buttons()   # la police/le thème ont pu changer les métriques
        self._update_mode_badge()
        if hasattr(self, "cfg_apply_btn"):
            self.cfg_apply_btn.setStyleSheet(theme.style("button.apply", "font-weight:bold;"))
        if hasattr(self, "_seq_hint"):
            self._seq_hint.setStyleSheet(theme.style("text.muted", "font-size:11px;"))
        if hasattr(self, "_seq_run_btn"):
            self._seq_run_btn.setStyleSheet(theme.style("button.start", "font-weight:bold;"))
        if hasattr(self, "seq_edit_path"):
            self.seq_edit_path.setStyleSheet(theme.style("text.muted"))
        if hasattr(self, "_seq_help_box"):
            self._seq_help_box.setHtml(self._seq_help_html(
                list(self.ctrl.cfg.all_labels), list(self.ctrl.cfg.temperatures),
                list(self.ctrl.cfg.relay_labels)))
        if hasattr(self, "_seq_highlighter"):
            self._seq_highlighter.apply_theme_colors()
        for row in self.rows.values():
            row.reset_pending_cache()

    def _toggle_alarm(self, on: bool) -> None:
        self._alarm_enabled = on
        self._settings.setValue("alarm", on)

    def _toggle_confirm_emergency(self, on: bool) -> None:
        self._confirm_emergency = on
        self._settings.setValue("confirm_emergency", on)

    # -------------------------------------------------- dialogues / titre
    def _dialog_dir(self) -> str:
        """Dernier dossier utilisé dans les dialogues de fichiers (QSettings)."""
        return self._settings.value("last_dir", "", type=str)

    def _remember_dir(self, path) -> None:
        try:
            self._settings.setValue("last_dir", str(Path(path).resolve().parent))
        except Exception:
            pass

    def _on_editor_modified(self, changed: bool) -> None:
        self._seq_modified = bool(changed)
        self._update_title()

    def _update_cfg_labels(self) -> None:
        """Reflète le fichier de configuration courant (barre d'état + entête de
        l'onglet Configuration)."""
        name = Path(self._cfg_path).name
        if hasattr(self, "mode_badge"):
            self._update_mode_badge()
        if hasattr(self, "sb_cfg"):
            self.sb_cfg.setText(f"cfg : {name}")
        if hasattr(self, "cfg_header_label"):
            self.cfg_header_label.setText(
                f"Édition interactive de <b>{name}</b>. Les voies/groupes/capteurs "
                "renommés ou supprimés sont vérifiés à « Appliquer ».")

    def _update_title(self) -> None:
        base = f"ALIM_SEQ — Séquenceur d'alimentation  v{__version__}"
        name = ""
        if hasattr(self, "seq_edit_path"):
            p = self.seq_edit_path.text().strip()
            name = Path(p).name if p else ""
        star = "●" if self._seq_modified else ""
        suffix = f"  — {star}{name}" if (name or star) else ""
        if self.ctrl.cfg.simulate:
            suffix += "  — SIMULATION"
        self.setWindowTitle(base + suffix)

    def _menu_open_sequence(self) -> None:
        self.tabs.setCurrentIndex(2)   # onglet Éditeur
        self._seq_open()

    def _toggle_compact(self, on: bool) -> None:
        self._journal_box.setVisible(not on)

    def _menu_load_config(self) -> None:
        if self.runner.is_running:
            QtWidgets.QMessageBox.information(self, self.tr("Profile"), self.tr("Stop the sequence first."))
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Charger une configuration (profil)", self._dialog_dir(),
            "Configuration (*.json);;Tous (*)")
        if not path:
            return
        try:
            load_config(path)   # valide avant de basculer
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Configuration invalide", str(exc))
            return
        if QtWidgets.QMessageBox.question(
                self, "Charger le profil",
                self.tr("Switch to this profile and reload the hardware?\n\n{}").format(path)
        ) != QtWidgets.QMessageBox.Yes:
            return
        # Modèle document : on BASCULE sur le fichier choisi (config.json n'est
        # plus touché).
        self._remember_dir(path)
        self._reload_controller(Path(path))

    def _menu_save_config_as(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Enregistrer la configuration sous…", self._dialog_dir(),
            "Configuration (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        # Sérialise l'ÉTAT COURANT de l'onglet Configuration (pas une copie), puis
        # bascule dessus (comportement « Enregistrer sous » standard).
        if not self._write_config_to(Path(path)):
            return
        self._cfg_path = Path(path).resolve()
        self._settings.setValue("last_profile", str(self._cfg_path))
        self._remember_dir(path)
        self._update_cfg_labels()
        self.cfg_status.setText(self.tr("✓ Saved to {}.").format(self._cfg_path.name))
        self.cfg_status.setStyleSheet(theme.style("text.ok"))
        self.ctrl.log(self.tr("Configuration saved as: {}").format(self._cfg_path))

    def _about(self) -> None:
        mode = self.tr("SIMULATION") if self.ctrl.cfg.simulate else self.tr("REAL HARDWARE")
        log_path = Path("logs/alim_seq.log").resolve()
        QtWidgets.QMessageBox.about(
            self, self.tr("About ALIM_SEQ"),
            self.tr(
                "<b>ALIM_SEQ</b> — Power-supply sequencer v{version}<br><br>"
                "R&S HMP (4040/4030/2030/2020) control + NI acquisition.<br>"
                "Sequences, servo control, thermal monitoring and safety.<br>"
                "Qt interface (PySide6).<br><br>"
                "<b>Mode:</b> {mode}<br>"
                "<b>Configuration:</b> {cfg}<br>"
                "<b>Log:</b> {log}<br><br>"
                "<b>Test folders:</b> each recording creates "
                "<code>logs/essais/YYYYMMDD_HHMMSS[_&lt;name&gt;]/</code> (measurements, "
                "config, sequence, log, metadata) from which the "
                "<b>PDF test report</b> can be regenerated at any time "
                "(<i>File → Generate a test report…</i>). The report issues no "
                "compliance verdict: the conclusion is the operator's.<br><br>"
                "<i>Laboratory use — check the configuration limits before "
                "any test on real hardware.</i>").format(
                    version=__version__, mode=mode, cfg=self._cfg_path, log=log_path))

    def _show_shortcuts(self) -> None:
        QtWidgets.QMessageBox.information(
            self, self.tr("Keyboard shortcuts"),
            "<table cellpadding='4'>"
            f"<tr><td><b>Ctrl+Shift+X</b></td><td>{self.tr('Emergency stop')}</td></tr>"
            f"<tr><td><b>Ctrl+S</b></td><td>{self.tr('Save the sequence')}</td></tr>"
            f"<tr><td><b>Ctrl+O</b></td><td>{self.tr('Open a sequence')}</td></tr>"
            f"<tr><td><b>F5</b></td><td>{self.tr('Check the sequence')}</td></tr>"
            f"<tr><td><b>Ctrl+Enter</b></td><td>{self.tr('Load and run the sequence')}</td></tr>"
            f"<tr><td><b>Ctrl+R</b></td><td>{self.tr('Start/stop recording')}</td></tr>"
            f"<tr><td><b>Ctrl+M</b></td><td>{self.tr('Place an operator marker')}</td></tr>"
            "</table>")

    def _manual_path(self):
        """Path to the user manual, in the current language when available:
        PyInstaller bundle (_MEIPASS/docs) or source tree (root/docs). The English
        manual is USER_MANUAL.md, the French one MANUEL_UTILISATEUR.md; falls back to
        the other language, then None if neither is found."""
        from pathlib import Path
        # Preferred filename first (current language), then the other as fallback.
        names = (["USER_MANUAL.md", "MANUEL_UTILISATEUR.md"]
                 if i18n.current_language() != "fr"
                 else ["MANUEL_UTILISATEUR.md", "USER_MANUAL.md"])
        roots = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass) / "docs")
        roots.append(Path(__file__).resolve().parents[2] / "docs")
        cands = [root / name for name in names for root in roots]
        return next((p for p in cands if p.exists()), None)

    def _show_manual(self) -> None:
        md_path = self._manual_path()
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(self.tr("User manual"))
        dlg.resize(860, 720)
        lay = QtWidgets.QVBoxLayout(dlg)
        browser = QtWidgets.QTextBrowser()
        browser.setOpenExternalLinks(True)
        if md_path is not None:
            text = md_path.read_text(encoding="utf-8")
            # Retire l'en-tête YAML (--- … ---) que le rendu Markdown afficherait brut.
            if text.startswith("---"):
                end = text.find("\n---", 3)
                if end != -1:
                    text = text[end + 4:]
            browser.setMarkdown(text)
        else:
            browser.setHtml(f"<p>{self.tr('Manual not found in this installation.')}</p>")
        lay.addWidget(browser)
        bar = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        pdf = md_path.with_suffix(".pdf") if md_path is not None else None
        if pdf is not None and pdf.exists():
            b = bar.addButton(self.tr("Open the PDF"), QtWidgets.QDialogButtonBox.ActionRole)
            b.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(str(pdf))))
        bar.rejected.connect(dlg.reject)
        bar.accepted.connect(dlg.accept)
        lay.addWidget(bar)
        dlg.exec()

    def _show_seq_reference(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(self.tr("Sequence command reference"))
        dlg.resize(560, 620)
        lay = QtWidgets.QVBoxLayout(dlg)
        browser = QtWidgets.QTextBrowser()
        browser.setHtml(self._seq_help_html(list(self.ctrl.cfg.all_labels),
                                            list(self.ctrl.cfg.temperatures),
                                            list(self.ctrl.cfg.relay_labels)))
        lay.addWidget(browser)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn.rejected.connect(dlg.reject); btn.accepted.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec()

    def _rebuild_tabs(self) -> None:
        """(Re)construit tous les onglets — appelé à l'init et après rechargement."""
        while self.tabs.count():
            w = self.tabs.widget(0); self.tabs.removeTab(0); w.deleteLater()
        self.rows.clear(); self.temp_rows.clear(); self.relay_rows.clear(); self.plot = None
        self.tabs.addTab(self._build_control_tab(), self.tr("🎛  Control"))
        self.tabs.addTab(self._build_config_tab(), self.tr("⚙  Configuration"))
        self.tabs.addTab(self._build_seq_editor_tab(), self.tr("📝  Sequence editor"))
        # Le graphe trace températures ET tensions/courants par voie : on l'affiche
        # dès qu'il y a des voies (donc quasi toujours), même sans capteur de température.
        if self.ctrl.cfg.channels or self.ctrl.cfg.temperatures:
            self.tabs.addTab(self._build_plot_tab(), self.tr("📈  Chart"))
        # Réglage à chaud de la simulation (mode simulation uniquement).
        if self.ctrl.cfg.simulate:
            self.tabs.addTab(self._build_sim_tab(), self.tr("🧪  Simulation"))

    def _build_plot_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget(); l = QtWidgets.QVBoxLayout(w)
        warn = {n: s.warning for n, s in self.ctrl.cfg.temperatures.items()}
        crit = {n: s.critical for n, s in self.ctrl.cfg.temperatures.items()}
        self.plot = TempPlotQt(list(self.ctrl.cfg.temperatures), warn, crit,
                               channels=list(self.ctrl.cfg.channels))

        ctl = QtWidgets.QHBoxLayout()
        ctl.addWidget(QtWidgets.QLabel("Grandeur :"))
        qty = QtWidgets.QComboBox()
        # « Températures » n'est proposé que si des capteurs sont configurés.
        if self.ctrl.cfg.temperatures:
            qty.addItem(self.tr("Temperatures (°C)"), "temp")
        qty.addItem("Courants (A)", "current")
        qty.addItem("Tensions (V)", "voltage")
        qty.setToolTip(self.tr("Plotted quantity. Hover the chart to read values; "
                               "click a curve name in the legend to hide/show it."))
        qty.currentIndexChanged.connect(lambda i: self.plot.set_mode(qty.itemData(i)))
        # Synchronise le mode initial du graphe avec le 1er élément (sans capteur,
        # c'est « Courants » : le mode 'temp' n'aurait rien à tracer).
        self.plot.set_mode(qty.currentData())
        ctl.addWidget(qty)
        if self.ctrl.cfg.temperatures:
            ctl.addWidget(QtWidgets.QLabel("(── mesure · – – warning · ··· critical)"))
        ctl.addStretch(1)
        self._plot_pause_btn = QtWidgets.QPushButton("⏸ Pause")
        self._plot_pause_btn.setCheckable(True)
        self._plot_pause_btn.toggled.connect(self._toggle_plot_pause)
        ctl.addWidget(self._plot_pause_btn)
        clear = QtWidgets.QPushButton("🗑 Effacer"); clear.clicked.connect(
            lambda: self.plot.set_sensors(self.plot.sensors))
        ctl.addWidget(clear)
        export = QtWidgets.QPushButton("📷 PNG"); export.clicked.connect(self._export_plot_png)
        ctl.addWidget(export)
        export_csv = QtWidgets.QPushButton("📄 CSV"); export_csv.clicked.connect(self._export_plot_csv)
        ctl.addWidget(export_csv)
        ctl.addWidget(QtWidgets.QLabel(self.tr("Window:")))
        win_combo = QtWidgets.QComboBox()
        for s in ("60 s", "120 s", "300 s", "600 s"):
            win_combo.addItem(s)
        win_combo.setCurrentText("120 s")
        win_combo.currentTextChanged.connect(
            lambda t: setattr(self.plot, "window_s", float(t.split()[0])))
        ctl.addWidget(win_combo)
        l.addLayout(ctl)
        l.addWidget(self.plot, 1)
        return w

    def _toggle_plot_pause(self, on: bool) -> None:
        self._plot_paused = on
        self._plot_pause_btn.setText("▶ Reprendre" if on else "⏸ Pause")

    def _export_plot_png(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Exporter le graphe", "graphe.png", "Image PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if self.plot.grab().save(path):
            self.ctrl.log(self.tr("Chart exported: {}").format(path))
        else:
            QtWidgets.QMessageBox.warning(self, "Export", "Échec de l'enregistrement du PNG.")

    def _export_plot_csv(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, self.tr("Export chart data"), "temperatures.csv", "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            self.plot.export_csv(path)
            self.ctrl.log(self.tr("Chart data exported: {}").format(path))
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Export CSV", str(exc))

    # Largeurs mini et alignements partagés des colonnes (voies + groupes + en-têtes
    # alignés). Le dernier ressort (stretch) absorbe l'espace pour ne pas étirer les
    # colonnes ni le bouton « Appliquer ».
    _COLW = [64, 92, 92, 116, 78, 104, 104, 70]
    _HALIGN = ["l", "l", "l", "c", "l", "r", "r", "l"]
    _ALIGN = {"l": QtCore.Qt.AlignLeft, "c": QtCore.Qt.AlignCenter, "r": QtCore.Qt.AlignRight}

    def _setup_grid(self, grid: QtWidgets.QGridLayout, last_col: int) -> None:
        for col, h in enumerate(ChannelRowQt.headers()):
            lab = QtWidgets.QLabel(f"<i>{h}</i>")
            lab.setAlignment(self._ALIGN[self._HALIGN[col]] | QtCore.Qt.AlignVCenter)
            grid.addWidget(lab, 0, col)
        for c, w in enumerate(self._COLW):
            grid.setColumnMinimumWidth(c, w)
        grid.setColumnStretch(last_col + 1, 1)

    def _build_control_tab(self) -> QtWidgets.QWidget:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        scroll.setWidget(inner)
        v = QtWidgets.QVBoxLayout(inner)

        # (Le mode SIMULATION / MATÉRIEL RÉEL est affiché en badge permanent dans
        # la barre de sécurité, au-dessus des onglets.)

        # Voies
        chan_box = QtWidgets.QGroupBox("Voies d'alimentation")
        cg = QtWidgets.QGridLayout(chan_box)
        self._setup_grid(cg, last_col=7)
        for r, label in enumerate(self.ctrl.cfg.channels, start=1):
            self.rows[label] = ChannelRowQt(cg, r, label, self.ctrl)
        v.addWidget(chan_box)

        # Groupes série
        if self.ctrl.cfg.groups:
            grp_box = QtWidgets.QGroupBox(self.tr("Series channels (voltage = sum)"))
            gg = QtWidgets.QGridLayout(grp_box)
            self._setup_grid(gg, last_col=8)
            for r, (gname, g) in enumerate(self.ctrl.cfg.groups.items(), start=1):
                self.rows[gname] = ChannelRowQt(gg, r, gname, self.ctrl)
                gg.addWidget(QtWidgets.QLabel("= " + " + ".join(g.members)), r, 8)
            v.addWidget(grp_box)

        # Températures
        if self.ctrl.cfg.temperatures:
            tbox = QtWidgets.QGroupBox(self.tr("Temperatures"))
            tg = QtWidgets.QGridLayout(tbox)
            tg.setHorizontalSpacing(18)
            tg.setColumnMinimumWidth(0, 100)   # nom du capteur (affiché en entier)
            tg.setColumnMinimumWidth(1, 110)   # pastille de mesure/statut
            for r, (name, s) in enumerate(self.ctrl.cfg.temperatures.items()):
                self.temp_rows[name] = TempRowQt(tg, r, name, s.warning, s.critical)
            tg.setColumnStretch(3, 1)          # l'espace restant part à droite
            v.addWidget(tbox)

        # Relais (actionneurs) — affichés seulement si la config en déclare.
        if self.ctrl.cfg.relay_labels:
            rlbox = QtWidgets.QGroupBox("Relais")
            rlg = QtWidgets.QGridLayout(rlbox)
            rlg.setHorizontalSpacing(18)
            for col, h in enumerate(RelayRowQt.headers()):
                if h:
                    lab = QtWidgets.QLabel(h)
                    fh = lab.font(); fh.setBold(True); lab.setFont(fh)
                    lab.setStyleSheet(theme.style("text.muted"))
                    rlg.addWidget(lab, 0, col)
            for r, label in enumerate(self.ctrl.cfg.relay_labels, start=1):
                self.relay_rows[label] = RelayRowQt(rlg, r, label, self.ctrl)
            rlg.setColumnStretch(3, 1)
            v.addWidget(rlbox)

        # Séquence
        sbox = QtWidgets.QGroupBox(self.tr("Sequence"))
        sl = QtWidgets.QGridLayout(sbox)
        sl.addWidget(QtWidgets.QLabel(self.tr("File:")), 0, 0)
        last_seq = self._settings.value("last_seq", "", type=str)
        default_seq = last_seq if (last_seq and Path(last_seq).exists()) else "sequences/demo.seq"
        self.seq_path = QtWidgets.QLineEdit(default_seq)
        sl.addWidget(self.seq_path, 0, 1)
        browse = QtWidgets.QPushButton(self.tr("Browse…")); browse.clicked.connect(self._browse)
        sl.addWidget(browse, 0, 2)
        load = QtWidgets.QPushButton(self.tr("Load/Check")); load.clicked.connect(self._load)
        sl.addWidget(load, 0, 3)
        # Séquence d'arrêt (optionnelle : vide = extinction auto en ordre inverse).
        sl.addWidget(QtWidgets.QLabel(self.tr("Shutdown seq.:")), 1, 0)
        self.shutdown_path = QtWidgets.QLineEdit(self.ctrl.shutdown_path or "")
        self.shutdown_path.textChanged.connect(
            lambda t: self.ctrl.set_shutdown_sequence(t.strip() or None, log=False))
        sl.addWidget(self.shutdown_path, 1, 1)
        browse_sd = QtWidgets.QPushButton(self.tr("Browse…")); browse_sd.clicked.connect(self._browse_shutdown)
        sl.addWidget(browse_sd, 1, 2)
        verify_sd = QtWidgets.QPushButton(self.tr("Check")); verify_sd.clicked.connect(self._verify_shutdown)
        sl.addWidget(verify_sd, 1, 3)
        hint = QtWidgets.QLabel(self.tr("(empty = automatic channel power-off in reverse order)"))
        hint.setStyleSheet(theme.style("text.muted", "font-size:11px;"))
        self._seq_hint = hint
        sl.addWidget(hint, 2, 0, 1, 4)
        self.btn_start = QtWidgets.QPushButton(self.tr("▶ Start the sequence"))
        self.btn_start.setStyleSheet(theme.style("button.start", "font-weight:bold;"))
        self.btn_start.setToolTip(self.tr("Loads the file above and runs it (Ctrl+Enter from the editor)"))
        self.btn_start.clicked.connect(lambda: self._start_sequence())
        sl.addWidget(self.btn_start, 3, 0, 1, 4)
        self.btn_pause = QtWidgets.QPushButton(self.tr("⏸ Pause"))
        self.btn_pause.setEnabled(False)
        self.btn_pause.setToolTip(self.tr("Suspend/resume the sequence (also freezes WAITs)"))
        self.btn_pause.clicked.connect(self._toggle_pause)
        sl.addWidget(self.btn_pause, 4, 0, 1, 2)
        # Pas-à-pas : case + bouton « Étape suivante » (actif seulement si une
        # séquence tourne en mode pas-à-pas).
        self.chk_step = QtWidgets.QCheckBox(self.tr("Step-by-step"))
        self.chk_step.setToolTip(self.tr("Runs the sequence action by action (each action "
                                         "waits for “Next step”)."))
        self.chk_step.toggled.connect(self._toggle_step_mode)
        sl.addWidget(self.chk_step, 4, 2)
        self.btn_step_next = QtWidgets.QPushButton(self.tr("▶| Next step"))
        self.btn_step_next.setEnabled(False)
        self.btn_step_next.setToolTip(self.tr("Allows the next action in step-by-step mode"))
        self.btn_step_next.clicked.connect(lambda: self.runner.step_once())
        sl.addWidget(self.btn_step_next, 4, 3)
        # Progression : barre k/n + temps restant estimé.
        self.seq_progress = QtWidgets.QProgressBar()
        self.seq_progress.setTextVisible(True)
        sl.addWidget(self.seq_progress, 5, 0, 1, 3)
        self.seq_remaining = QtWidgets.QLabel("")
        self.seq_remaining.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        sl.addWidget(self.seq_remaining, 5, 3)
        self.seq_status = QtWidgets.QLabel(self.tr("No sequence loaded."))
        sl.addWidget(self.seq_status, 6, 0, 1, 4)
        v.addWidget(sbox)

        # Enregistrement
        rbox = QtWidgets.QGroupBox(self.tr("Measurement recording"))
        rl = QtWidgets.QHBoxLayout(rbox)
        self.btn_rec = QtWidgets.QPushButton(self.tr("● Start recording"))
        self.btn_rec.clicked.connect(self._toggle_record)
        rl.addWidget(self.btn_rec)
        self.auto_rec = QtWidgets.QCheckBox(self.tr("Record during the sequence"))
        self.auto_rec.setChecked(self._settings.value("auto_rec", True, type=bool))
        self.auto_rec.toggled.connect(lambda on: self._settings.setValue("auto_rec", on))
        rl.addWidget(self.auto_rec)
        # Marqueur opérateur : horodate une note dans le journal (reprise comme repère
        # sur le graphe live ET comme badge numéroté du rapport) — « c'est ici que… ».
        self.btn_marker = QtWidgets.QPushButton(self.tr("📌 Marker"))
        self.btn_marker.setToolTip(self.tr("Place a timestamped marker (note) — Ctrl+M. "
                                           "Appears on the chart and in the test report."))
        self.btn_marker.clicked.connect(self._add_marker)
        rl.addWidget(self.btn_marker)
        rl.addStretch(1)
        v.addWidget(rbox)

        # Matériel : la reconnexion reste ici ; les commandes VITALES (arrêt
        # d'urgence, séquentiel d'arrêt, réarmer, tout OFF) sont dans la barre de
        # sécurité permanente, au-dessus des onglets.
        ebox = QtWidgets.QHBoxLayout()
        self.btn_reconnect = QtWidgets.QPushButton(self.tr("Reconnect"))
        self.btn_reconnect.setToolTip(self.tr("Reconnect the hardware (VISA / NI-DAQmx) after a communication loss"))
        self.btn_reconnect.clicked.connect(self._reconnect)
        ebox.addWidget(self.btn_reconnect)
        ebox.addStretch(1)
        v.addLayout(ebox)
        v.addStretch(1)
        return scroll

    # ------------------------------------------------------------- actions
    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.tr("Choose a sequence"), self._dialog_dir(), self.tr("Sequence (*.seq *.txt);;All (*)"))
        if path:
            self.seq_path.setText(path)
            self._remember_dir(path)

    def _load(self) -> bool:
        path = Path(self.seq_path.text())
        if not path.exists():
            QtWidgets.QMessageBox.critical(self, self.tr("File not found"), str(path))
            return False
        try:
            text = path.read_text(encoding="utf-8")
            self._actions = parse_sequence(text, set(self.ctrl.cfg.all_labels),
                                           set(self.ctrl.cfg.temperatures),
                                           set(self.ctrl.cfg.relay_labels))
        except (SequenceError, OSError) as exc:
            QtWidgets.QMessageBox.critical(self, self.tr("Invalid sequence"), str(exc))
            self._seq_status = (self.tr("Invalid sequence."), "text.error")
            return False
        self._seq_text = text
        self._seq_status = (self.tr("{} action(s) from {}.").format(len(self._actions), path.name), "text.ok")
        return True

    def _browse_shutdown(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.tr("Choose a shutdown sequence"), self._dialog_dir(),
            self.tr("Sequence (*.seq *.txt);;All (*)"))
        if path:
            self.shutdown_path.setText(path)
            self._remember_dir(path)

    def _verify_shutdown(self) -> None:
        p = self.shutdown_path.text().strip()
        if not p:
            self.ctrl.set_shutdown_sequence(None)
            QtWidgets.QMessageBox.information(
                self, self.tr("Shutdown sequence"),
                self.tr("Empty: automatic channel power-off in reverse order."))
            return
        path = Path(p)
        if not path.exists():
            QtWidgets.QMessageBox.critical(self, self.tr("File not found"), str(path))
            return
        try:
            parse_sequence(path.read_text(encoding="utf-8"),
                           set(self.ctrl.cfg.all_labels), set(self.ctrl.cfg.temperatures),
                           set(self.ctrl.cfg.relay_labels))
        except (SequenceError, OSError) as exc:
            QtWidgets.QMessageBox.critical(self, self.tr("Invalid shutdown sequence"), str(exc))
            return
        self.ctrl.set_shutdown_sequence(p)
        QtWidgets.QMessageBox.information(self, self.tr("Shutdown sequence"),
                                          self.tr("Valid file: {}").format(path.name))

    def _start_sequence(self, from_editor: bool = False) -> None:
        if self.runner.is_running:
            QtWidgets.QMessageBox.information(self, self.tr("Sequence"), self.tr("Already running."))
            return
        # Matériel non connecté (typiquement en mode réel sans banc branché) : refuser
        # AVANT tout, sinon la séquence échoue voie par voie et un enregistrement
        # aurait déjà été ouvert pour rien.
        if not self.ctrl.connected or self.ctrl.comm_lost:
            QtWidgets.QMessageBox.warning(
                self, self.tr("Hardware not connected"),
                self.tr("The hardware is not connected: cannot start a sequence.\n\n"
                        "Check the link (VISA / NI-DAQmx) then “Reconnect”."))
            return
        if self.ctrl.tripped:
            QtWidgets.QMessageBox.warning(self, self.tr("Safety"), self.tr("Rearm the safety before starting."))
            return
        if not self._actions and not self._load():
            return
        if self.auto_rec.isChecked() and not self.ctrl.is_recording:
            nom, operateur = self._ask_essai_meta()
            self._auto_report_done = False
            self.ctrl.start_recording(nom=nom, operateur=operateur)
        self._seq_from_editor = from_editor
        self._seq_run_line = 0
        self.ctrl.start_user_sequence(self._actions, text=self._seq_text)
        self.btn_start.setEnabled(False)

    def _emergency(self) -> None:
        # Sans confirmation par défaut (coup de poing). Dialogue seulement si
        # l'option « Confirmer l'arrêt d'urgence » est activée.
        if self._confirm_emergency and QtWidgets.QMessageBox.question(
                self, self.tr("Emergency stop"),
                self.tr("ABRUPT, immediate cut-off of all channels.\nConfirm?")
        ) != QtWidgets.QMessageBox.Yes:
            return
        self.ctrl.emergency_stop(self.tr("EMERGENCY STOP (operator)"))

    def _reset(self) -> None:
        if self.runner.is_running:
            QtWidgets.QMessageBox.information(self, self.tr("Rearm"), self.tr("Stop the sequence first."))
            return
        self.ctrl.reset_safety()

    def _reconnect(self) -> None:
        if self.runner.is_running:
            QtWidgets.QMessageBox.information(self, self.tr("Reconnection"), self.tr("Stop the sequence first."))
            return
        self.btn_reconnect.setText(self.tr("Reconnecting…"))
        self._connecting = True

        def done(result):
            self.btn_reconnect.setText(self.tr("Reconnect"))
            self._connecting = False
            if result is True:
                QtWidgets.QMessageBox.information(self, self.tr("Reconnection"), self.tr("Hardware reconnected."))
            else:
                QtWidgets.QMessageBox.critical(self, self.tr("Reconnection"),
                                               self.tr("Failure:\n\n{}").format(self.ctrl.connect_error))

        if not self._start_hw_task(self.ctrl.reconnect, done, done, controls=True):
            self.btn_reconnect.setText(self.tr("Reconnect"))
            self._connecting = False

    def _all_off(self) -> None:
        for label in self.ctrl.cfg.channels:
            self.ctrl.set_output(label, False)
        self.ctrl.log(self.tr("All channels cut off (All OFF)."))

    def _ask_essai_meta(self) -> tuple[str, str]:
        """Petit dialogue facultatif « Nom de l'essai / Opérateur ». Les deux
        champs sont facultatifs ; l'opérateur est mémorisé (QSettings). Entrée
        valide, Échap laisse les champs vides. Retourne toujours (nom, opérateur)
        — l'enregistrement démarre dans tous les cas."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(self.tr("New test"))
        form = QtWidgets.QFormLayout(dlg)
        nom_edit = QtWidgets.QLineEdit()
        nom_edit.setPlaceholderText(self.tr("(optional)"))
        op_edit = QtWidgets.QLineEdit(self._settings.value("operateur", "", type=str))
        op_edit.setPlaceholderText(self.tr("(optional)"))
        form.addRow(self.tr("Test name:"), nom_edit)
        form.addRow(self.tr("Operator:"), op_edit)
        hint = QtWidgets.QLabel(self.tr("This information will appear in the test report."))
        hint.setStyleSheet(theme.style("text.muted", "font-size:11px;"))
        form.addRow(hint)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        nom_edit.setFocus()
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            nom, operateur = nom_edit.text().strip(), op_edit.text().strip()
            self._settings.setValue("operateur", operateur)
            return nom, operateur
        return "", ""

    # ------------------------------------------------------ rapport d'essai
    def _ask_conclusion(self, initial: str = ""):
        """Dialogue multiligne de conclusion (facultative). Retourne le texte
        (éventuellement vide) ou None si l'opérateur annule (pas de rapport)."""
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(self.tr("Test conclusion"))
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(QtWidgets.QLabel(self.tr(
            "Operator conclusion (optional) — the report issues no compliance "
            "verdict:")))
        edit = QtWidgets.QPlainTextEdit(initial)
        edit.setMinimumSize(440, 150)
        v.addWidget(edit)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        edit.setFocus()
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            return edit.toPlainText().strip()
        return None

    def _run_report_task(self, dossier, conclusion: str, auto: bool = False) -> None:
        """Génère rapport.html + rapport.pdf dans ``dossier`` via un worker (jamais
        dans le thread GUI)."""
        from ..rapport import generer_rapport

        dossier = Path(dossier)
        self.ctrl.log(self.tr("Generating the test report…"))
        task = Task(lambda: generer_rapport(dossier, conclusion=conclusion), self)
        self._report_tasks.append(task)
        task.done.connect(lambda pdf: self._on_report_done(pdf, auto))
        task.failed.connect(
            lambda m: self.ctrl.log(self.tr("Report generation failed: {}").format(m)))
        task.finished.connect(
            lambda: self._report_tasks.remove(task) if task in self._report_tasks else None)
        task.start()

    def _on_report_done(self, pdf, auto: bool) -> None:
        pdf = Path(pdf)
        self.ctrl.log(self.tr("Test report generated: {}").format(pdf))
        if auto:
            return   # cas déclenchement de sécurité : silencieux (journal seulement)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(self.tr("Test report"))
        box.setText(self.tr("Report generated:\n{}").format(pdf))
        open_btn = box.addButton(self.tr("Open the PDF"), QtWidgets.QMessageBox.AcceptRole)
        box.addButton(QtWidgets.QMessageBox.Close)
        box.exec()
        if box.clickedButton() is open_btn:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(pdf)))

    def _pick_essai_dossier(self, title: str):
        """Sélecteur d'un dossier d'essai (liste ``logs/essais/…``, étiqueté par
        l'issue). Retourne ``(dossier, meta)`` ou ``(None, None)`` si annulé/aucun."""
        import json
        base = Path("logs/essais")
        dossiers = sorted((d for d in base.glob("*") if d.is_dir()), reverse=True) \
            if base.exists() else []
        if not dossiers:
            QtWidgets.QMessageBox.information(
                self, title, self.tr("No test folder in logs/essais."))
            return None, None
        labels, by_label = [], {}
        for d in dossiers:
            meta = {}
            try:
                meta = json.loads((d / "essai.json").read_text(encoding="utf-8"))
            except Exception:
                pass
            issue = (meta.get("issue") or {}).get("issue", "?")
            label = f"{d.name}  —  {self._issue_label(issue)}"
            labels.append(label)
            by_label[label] = (d, meta)
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, title, self.tr("Test folder:"), labels, 0, False)
        if not ok:
            return None, None
        return by_label[choice]

    def _menu_generate_report(self) -> None:
        dossier, meta = self._pick_essai_dossier(self.tr("Generate a test report"))
        if dossier is None:
            return
        conclusion = self._ask_conclusion((meta or {}).get("conclusion", ""))
        if conclusion is not None:
            self._run_report_task(dossier, conclusion)

    def _menu_replay_essai(self) -> None:
        """Ouvre une fenêtre de relecture (courbes rejouées) d'un essai enregistré."""
        dossier, _meta = self._pick_essai_dossier(self.tr("Reopen a test (replay)"))
        if dossier is None:
            return
        from .replay import open_replay_dialog
        dlg = open_replay_dialog(self, dossier, on_report=self._replay_report)
        self._replay_dialogs.append(dlg)
        dlg.finished.connect(
            lambda *_: self._replay_dialogs.remove(dlg)
            if dlg in self._replay_dialogs else None)

    def _replay_report(self, dossier) -> None:
        """Génère le rapport PDF depuis la fenêtre de relecture (demande la conclusion)."""
        conclusion = self._ask_conclusion()
        if conclusion is not None:
            self._run_report_task(dossier, conclusion)

    def _maybe_first_launch(self) -> None:
        """Au tout premier lancement, propose l'assistant de configuration (une fois)."""
        if self._settings.value("config_wizard_offered", False, type=bool):
            return
        self._settings.setValue("config_wizard_offered", True)
        r = QtWidgets.QMessageBox.question(
            self, self.tr("Welcome to ALIM_SEQ"),
            self.tr("Configure your bench now?\n\nThe wizard detects the power "
                    "supplies (VISA scan) and prepares a starting configuration. "
                    "You can relaunch it via File → Configuration wizard."),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if r == QtWidgets.QMessageBox.Yes:
            self._menu_config_wizard()

    def _menu_config_wizard(self) -> None:
        """Ouvre l'assistant ; la config générée est chargée dans l'éditeur pour revue."""
        from .config_wizard import ConfigWizard
        wiz = ConfigWizard(self, visa_backend=self.ctrl.cfg.visa_backend)
        if wiz.exec() != QtWidgets.QDialog.Accepted or not wiz.result_config:
            return
        import json
        raw = wiz.result_config
        self._fill_forms_from_raw(raw)
        self.cfg_json.setPlainText(json.dumps(raw, indent=2, ensure_ascii=False))
        # Bascule sur l'onglet Configuration pour revue avant application.
        for i in range(self.tabs.count()):
            if "Config" in self.tabs.tabText(i):
                self.tabs.setCurrentIndex(i)
                break
        QtWidgets.QMessageBox.information(
            self, self.tr("Configuration wizard"),
            self.tr("Configuration generated and loaded into the Configuration tab.\n"
                    "Check the channels (names, limits), then click "
                    "“✓ Apply (reload hardware)”."))

    def _menu_compare_essais(self) -> None:
        """Ouvre une fenêtre superposant les courbes de deux essais (recalées sur t=0)."""
        a, _ma = self._pick_essai_dossier(self.tr("Compare — 1st test (A)"))
        if a is None:
            return
        b, _mb = self._pick_essai_dossier(self.tr("Compare — 2nd test (B)"))
        if b is None:
            return
        from .replay import open_compare_dialog
        dlg = open_compare_dialog(self, a, b)
        self._replay_dialogs.append(dlg)
        dlg.finished.connect(
            lambda *_: self._replay_dialogs.remove(dlg)
            if dlg in self._replay_dialogs else None)

    def _issue_label(self, issue: str) -> str:
        return {"termine": self.tr("Completed"), "arret_utilisateur": self.tr("Interrupted"),
                "declenchement_securite": self.tr("SAFETY TRIP"),
                "en_cours": self.tr("in progress")}.get(issue, issue)

    def _menu_open_essais_dir(self) -> None:
        """« Où sont mes fichiers ? » : ouvre logs/essais/ dans l'explorateur."""
        base = Path("logs/essais")
        base.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(base.resolve())))

    def _add_marker(self) -> None:
        """Pose un repère opérateur horodaté : une note libre inscrite au journal
        (donc dans ``journal.log`` de l'essai en cours -> badge du rapport) et
        matérialisée sur le graphe live. Utilisable à tout moment (Ctrl+M)."""
        note, ok = QtWidgets.QInputDialog.getText(
            self, self.tr("Marker"), self.tr("Note (e.g. “I touched the capacitor”):"))
        if not ok:
            return
        note = (note or "").strip()
        self.ctrl.log(f"📌 {note}" if note else "📌 " + self.tr("marker"))
        if self.plot is not None:
            self.plot.mark(note or "📌")

    def _toggle_record(self) -> None:
        if self.ctrl.is_recording:
            essai = self.ctrl.essai
            dossier = essai.path if essai is not None else None
            self.ctrl.stop_recording()          # finalise essai.json (fin + issue)
            if dossier is not None and self._act_auto_report.isChecked():
                conclusion = self._ask_conclusion()
                if conclusion is not None:       # None = annulé -> pas de rapport
                    self._run_report_task(dossier, conclusion)
        else:
            nom, operateur = self._ask_essai_meta()
            self._auto_report_done = False
            self.ctrl.start_recording(nom=nom, operateur=operateur)

    def _toggle_pause(self) -> None:
        if not self.runner.is_running:
            return
        if self.runner.is_paused:
            self.runner.resume()
        else:
            self.runner.pause()

    def _toggle_step_mode(self, on: bool) -> None:
        self.runner.set_step_mode(on)

    def _update_seq_progress(self, running: bool) -> None:
        """Barre de progression k/n + temps restant estimé (en cours), ou durée
        totale estimée (au repos)."""
        total = len(self._actions)
        if running:
            k, n = self.runner.progress
            n = n or total
            self.seq_progress.setMaximum(max(1, n))
            self.seq_progress.setValue(min(k, n))
            self.seq_progress.setFormat(f"{min(k, n)}/{n}")
            remaining = estimate_duration(self._actions[k:]) if self._actions else 0.0
            self.seq_remaining.setText(self.tr("~{:.0f}s remaining").format(remaining) if remaining > 0 else "—")
        else:
            self.seq_progress.setMaximum(max(1, total))
            self.seq_progress.setValue(0)
            self.seq_progress.setFormat(self.tr("{} action(s)").format(total) if total else "")
            dur = estimate_duration(self._actions) if self._actions else 0.0
            self.seq_remaining.setText(
                self.tr("~{:.0f}s (excl. SERVO/WAIT_*)").format(dur) if dur > 0 else "")
        self.btn_step_next.setEnabled(running and self.runner.step_mode)

    # ------------------------------------------------------------- refresh
    def _refresh(self) -> None:
        snap = self.ctrl.snapshot()
        hw_enabled = not self._hw_busy
        stale = snap.stale_labels
        for label, row in self.rows.items():
            if label in snap.channels:
                # Une voie est périmée si son instrument a été sauté ; un groupe l'est
                # si au moins un de ses membres l'est.
                if label in self.ctrl.cfg.groups:
                    row_stale = any(m in stale for m in self.ctrl.cfg.groups[label].members)
                else:
                    row_stale = label in stale
                row.update(snap.channels[label], tripped=snap.tripped,
                           hw_enabled=hw_enabled, stale=row_stale)
        for name, trow in self.temp_rows.items():
            trow.update(snap.temperatures.get(name, float("nan")),
                        snap.temp_status.get(name, OK))
        for label, rrow in self.relay_rows.items():
            rrow.update(bool(snap.relays.get(label, False)),
                        tripped=snap.tripped, hw_enabled=hw_enabled)
        if self.plot is not None and not self._plot_paused:
            # Push même sans capteur : le graphe trace aussi les V/I par voie.
            vi = {lbl: (v.meas_voltage, v.meas_current)
                  for lbl, v in snap.channels.items() if lbl in self.ctrl.cfg.channels}
            self.plot.push(snap.temperatures, snap.temp_status, vi)

        level = snap.safety_status
        if self._connecting:
            text, level = self.tr("⏳ Connecting to the hardware…"), NA
        elif not snap.connected:
            text, level = self.tr("⛔ NOT CONNECTED — check VISA / NI-DAQmx then “Reconnect”"), CRITICAL
        elif snap.comm_lost:
            text, level = self.tr("⛔ COMMUNICATION LOST: {}").format(snap.safety_message), CRITICAL
        elif snap.tripped:
            text = self.tr("⛔ SAFETY TRIPPED: {}").format(snap.safety_message)
        elif snap.hw_fault:
            text, level = self.tr("⚠ {} — reset the supply then “Reconnect”").format(snap.hw_fault), FAULT
        elif snap.safety_message:
            text = self.tr("Safety: {} — {}").format(level, snap.safety_message)
        else:
            text = self.tr("Safety: OK")
        self.banner.setText(text)
        self.banner.setStyleSheet(theme.style(theme.level_token(level), "padding:6px;"))

        # Déclenchement de sécurité pendant un essai : dès la fin de la
        # désalimentation, générer AUTOMATIQUEMENT le rapport (conclusion vide,
        # sans dialogue) — cas d'usage le plus important. Une seule fois par essai.
        if (self.ctrl.is_recording and snap.tripped and not self._auto_report_done
                and not self.runner.is_running and not self.ctrl.is_shutting_down):
            essai = self.ctrl.essai
            if essai is not None:
                self._auto_report_done = True
                self.ctrl.log(self.tr("Safety trip: automatic test-report "
                                      "generation."))
                self._run_report_task(essai.path, "", auto=True)

        # Alerte sonore : bip à l'entrée en état critique, puis ~toutes les secondes.
        # (Pas d'alarme pendant une (re)connexion : « non connecté » est attendu.)
        critical = (not self._connecting) and (
            (not snap.connected) or snap.comm_lost or snap.tripped or level == CRITICAL)
        if critical and self._alarm_enabled:
            if not self._alarm_active or self._alarm_tick % 5 == 0:
                QtWidgets.QApplication.beep()
            self._alarm_tick += 1
            self._alarm_active = True
        else:
            self._alarm_active = False
            self._alarm_tick = 0

        # Barre d'état : pastille de connexion + mode + cadence + enregistrement.
        if not snap.connected or snap.comm_lost:
            self.sb_conn.setText("●"); self.sb_conn.setStyleSheet(theme.style("text.error"))
            self.sb_conn.setToolTip(self.tr("Hardware not connected"))
        else:
            self.sb_conn.setText("●"); self.sb_conn.setStyleSheet(theme.style("text.ok"))
            self.sb_conn.setToolTip(self.tr("Hardware connected"))
        self.sb_cadence.setText(self.tr("meas {:.2f}s · temp {:.2f}s").format(
            snap.meas_period, snap.temp_period))
        if self.ctrl.is_recording:
            dossier = self.ctrl.recording_dossier
            self.sb_rec.setText("⏺ REC" + (f" · {dossier}" if dossier else ""))
            self.sb_rec.setStyleSheet(theme.style("text.error", "font-weight:bold;"))
            self.sb_rec.setToolTip(self.tr("Current test folder: {}").format(dossier) if dossier else "")
        else:
            self.sb_rec.setText(""); self.sb_rec.setStyleSheet(""); self.sb_rec.setToolTip("")
        # Puissance totale délivrée (somme |V·I| des voies physiques).
        total_p = sum(abs(v.meas_voltage * v.meas_current)
                      for lbl, v in snap.channels.items() if lbl in self.ctrl.cfg.channels)
        self.sb_power.setText(f"P {total_p:5.1f} W")

        # Bouton « Réarmer » saillant tant que la sécurité est déclenchée. On ne
        # ré-applique le style (et ne ré-égalise la barre) que sur TRANSITION du trip
        # — pas à chaque tick — pour éviter un re-polish inutile à 5 Hz.
        if snap.tripped != self._reset_tripped:
            self._reset_tripped = snap.tripped
            self.btn_reset.setStyleSheet(self._reset_style(snap.tripped))
            self._equalize_safety_buttons()

        self.seq_status.setText(self._seq_status[0])
        self.seq_status.setStyleSheet(theme.style(self._seq_status[1]))
        running = self.runner.is_running
        if self.plot is not None and running != self._was_running:
            self.plot.mark("début séq." if running else "fin séq.")
        self._was_running = running
        if not running:
            # Démarrage possible seulement matériel connecté (grisé sinon : on ne
            # lance pas une séquence — ni un enregistrement — sans banc).
            self.btn_start.setEnabled(
                not self._hw_busy and snap.connected and not snap.comm_lost)
        self.btn_pause.setEnabled(running)
        self.btn_pause.setText(self.tr("▶ Resume") if (running and self.runner.is_paused) else self.tr("⏸ Pause"))
        self._update_seq_progress(running)
        self.btn_rec.setText(self.tr("■ Stop recording") if self.ctrl.is_recording
                             else self.tr("● Start recording"))
        self._update_editor_selections()

        for line in self.ctrl.drain_logs():
            self.log.appendPlainText(line)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # Modifications de séquence non enregistrées : Enregistrer / Ignorer / Annuler.
        if self._seq_modified:
            resp = QtWidgets.QMessageBox.question(
                self, self.tr("Unsaved sequence"),
                self.tr("The sequence being edited has unsaved changes.\n"
                        "Save before quitting?"),
                QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard
                | QtWidgets.QMessageBox.Cancel)
            if resp == QtWidgets.QMessageBox.Cancel:
                event.ignore()
                return
            if resp == QtWidgets.QMessageBox.Save:
                self._seq_save()
        self._settings.setValue("geometry", self.saveGeometry())
        if QtWidgets.QMessageBox.question(
                self, self.tr("Quit"), self.tr("Switch off the supplies and quit?")
        ) == QtWidgets.QMessageBox.Yes:
            try:
                self.runner.force_stop()
                self.ctrl.close()
            finally:
                event.accept()
        else:
            event.ignore()


def _set_app_icon(app) -> None:
    """Icône d'application, robuste au mode empaqueté (sys._MEIPASS). Silencieux
    si l'icône est introuvable."""
    import os
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "icon.ico"))
    # En dev : packaging/icon.ico à la racine du dépôt.
    root = Path(__file__).resolve().parents[2]
    candidates.append(str(root / "packaging" / "icon.ico"))
    for c in candidates:
        try:
            if os.path.exists(c):
                app.setWindowIcon(QtGui.QIcon(c))
                return
        except Exception:
            pass


# Languages the app ships translations for. "en" is the base (source) language.
SUPPORTED_LANGUAGES = {"en": "English", "fr": "Français"}

# Keeps installed QTranslator instances alive for the app lifetime.
_installed_translators: List[QtCore.QTranslator] = []


def resolve_language(settings: QtCore.QSettings) -> str:
    """Language to use: saved choice, else system locale, else English."""
    saved = settings.value("ui/language", "", type=str)
    if saved in SUPPORTED_LANGUAGES:
        return saved
    sys_lang = QtCore.QLocale.system().name().split("_")[0].lower()
    return sys_lang if sys_lang in SUPPORTED_LANGUAGES else "en"


def install_language(app: QtWidgets.QApplication, lang: str) -> None:
    """Install the GUI (.qm) and domain (gettext) catalogs for ``lang``.

    English is the base language: no ``.qm`` is needed (source strings are English)
    and the domain layer falls back to identity. Called once at startup.
    """
    global _installed_translators
    for tr in _installed_translators:
        app.removeTranslator(tr)
    _installed_translators = []

    i18n.set_language(lang)  # domain layer (controller logs, reports…)

    if lang != "en":
        qm = Path(__file__).resolve().parent / "i18n" / f"alim_seq_{lang}.qm"
        if qm.exists():
            translator = QtCore.QTranslator()
            if translator.load(str(qm)):
                app.installTranslator(translator)
                _installed_translators.append(translator)


def run(ctrl: Controller) -> None:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")  # homogeneous, modern rendering (Linux/Windows)
    app.setApplicationName("ALIM_SEQ")
    app.setOrganizationName("ALIM_SEQ")
    _set_app_icon(app)
    install_language(app, resolve_language(QtCore.QSettings("ALIM_SEQ", "ALIM_SEQ")))
    win = AlimSeqQtGUI(ctrl)
    win.show()
    app.exec()
