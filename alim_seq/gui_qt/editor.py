"""Onglet Éditeur de séquence : coloration syntaxique (SeqHighlighter) et
construction de l'onglet (EditorMixin, greffé sur la fenêtre principale)."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..sequencer import SequenceError, estimate_duration, parse_sequence
from . import theme


def read_text_tolerant(path) -> str:
    """Lit un fichier texte en UTF-8, avec repli latin-1 (qui ne peut pas échouer
    au décodage) pour tolérer les ``.seq`` créés sous Windows en CP1252. Peut
    lever ``OSError`` si le fichier est absent ou illisible — au décodage, jamais."""
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


class SeqHighlighter(QtGui.QSyntaxHighlighter):
    """Coloration syntaxique des séquences ``.seq`` : commandes, commentaires,
    nombres, clés ``clé=``, opérateurs, et voies/capteurs **connus** (les noms non
    reconnus restent neutres → les fautes de frappe sautent aux yeux)."""

    CMDS = {"SET", "SETV", "SETI", "VOLT", "VOLTAGE", "CURR", "CURRENT", "ON", "OFF",
            "WAIT", "DELAY", "RAMP", "SERVO", "SERVO_LIN", "SERVO_ADAPT",
            "WAIT_CURRENT", "WAIT_TEMP", "LOG", "ALL_OFF", "SHUTDOWN", "RELAY",
            "REPEAT", "END"}

    # Jeton de coloration -> (gras, italique) pour chaque catégorie syntaxique.
    _SYNTAX = {
        "f_cmd":     ("syntax.command", True, False),
        "f_comment": ("syntax.comment", False, True),
        "f_number":  ("syntax.number", False, False),
        "f_key":     ("syntax.key", False, False),
        "f_label":   ("syntax.label", True, False),
        "f_op":      ("syntax.op", False, False),
    }

    def __init__(self, document, labels=(), sensors=()):
        super().__init__(document)
        self.known = {s.upper() for s in labels} | {s.upper() for s in sensors}
        self.apply_theme_colors()

    def apply_theme_colors(self) -> None:
        """(Re)construit les formats de coloration depuis les jetons ``syntax.*`` du
        thème courant, puis re-colore le document (appelé à l'init et au changement
        de thème)."""
        for attr, (token, bold, italic) in self._SYNTAX.items():
            f = QtGui.QTextCharFormat()
            f.setForeground(QtGui.QColor(theme.pair(token)[1]))
            if bold:
                f.setFontWeight(QtGui.QFont.Bold)
            if italic:
                f.setFontItalic(True)
            setattr(self, attr, f)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        m = re.search(r"#|//", text)
        cstart = m.start() if m else len(text)
        ms = re.match(r"\s*([A-Za-z_]+)", text)
        if ms and ms.group(1).upper() in self.CMDS and ms.start(1) < cstart:
            self.setFormat(ms.start(1), len(ms.group(1)), self.f_cmd)
        for mm in re.finditer(r"[-+]?\d*\.?\d+", text):
            if mm.start() < cstart:
                self.setFormat(mm.start(), len(mm.group()), self.f_number)
        for mm in re.finditer(r"<=|>=|==|!=|<|>", text):
            if mm.start() < cstart:
                self.setFormat(mm.start(), len(mm.group()), self.f_op)
        for mm in re.finditer(r"\b([A-Za-z_]+)=", text):
            if mm.start() < cstart:
                self.setFormat(mm.start(1), len(mm.group(1)), self.f_key)
        for mm in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text):
            if mm.start() < cstart and mm.group().upper() in self.known:
                self.setFormat(mm.start(), len(mm.group()), self.f_label)
        if cstart < len(text):
            self.setFormat(cstart, len(text) - cstart, self.f_comment)


class CompletingPlainTextEdit(QtWidgets.QPlainTextEdit):
    """Éditeur de texte avec auto-complétion sur le mot courant (commandes,
    voies, capteurs). Recette standard QCompleter + QPlainTextEdit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._completer = None

    def set_completer(self, completer: QtWidgets.QCompleter) -> None:
        self._completer = completer
        completer.setWidget(self)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.activated.connect(self._insert_completion)

    def set_completion_words(self, words) -> None:
        if self._completer is not None:
            self._completer.setModel(
                QtCore.QStringListModel(sorted(set(words)), self._completer))

    def _insert_completion(self, completion: str) -> None:
        if self._completer.widget() is not self:
            return
        tc = self.textCursor()
        extra = len(completion) - len(self._completer.completionPrefix())
        tc.movePosition(QtGui.QTextCursor.Left)
        tc.movePosition(QtGui.QTextCursor.EndOfWord)
        tc.insertText(completion[-extra:] if extra > 0 else "")
        self.setTextCursor(tc)

    def _word_under_cursor(self) -> str:
        tc = self.textCursor()
        tc.select(QtGui.QTextCursor.WordUnderCursor)
        return tc.selectedText()

    def keyPressEvent(self, event) -> None:
        c = self._completer
        if c is not None and c.popup().isVisible():
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter,
                               QtCore.Qt.Key_Escape, QtCore.Qt.Key_Tab, QtCore.Qt.Key_Backtab):
                event.ignore()   # géré par le popup de complétion
                return
        super().keyPressEvent(event)
        if c is None:
            return
        prefix = self._word_under_cursor()
        if len(prefix) < 2:
            c.popup().hide()
            return
        if prefix != c.completionPrefix():
            c.setCompletionPrefix(prefix)
            c.popup().setCurrentIndex(c.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(c.popup().sizeHintForColumn(0)
                      + c.popup().verticalScrollBar().sizeHint().width())
        c.complete(rect)


class EditorMixin:
    """Onglet Éditeur de séquence, greffé sur :class:`AlimSeqQtGUI`."""

    def _seq_rows(self):
        tr = self.tr
        return [
            ("SET", tr("channel V [I]"), tr("voltage + current limit")),
            ("SETV", tr("channel = expr"), tr("voltage via formula")),
            ("SETI", tr("channel = expr"), tr("current limit via formula")),
            ("ON", tr("channel"), tr("switch on")),
            ("OFF", tr("channel"), tr("switch off")),
            ("WAIT", tr("seconds"), tr("pause (interruptible)")),
            ("RAMP", tr("channel Vend duration"), tr("ramp from current value")),
            ("RAMP", tr("channel Vstart Vend duration [steps]"),
             tr("explicit ramp ([steps]=number of steps, integer≥2)")),
            ("SERVO_LIN", tr("set measured Itarget"), tr("fixed-step servo (SERVO=alias)")),
            ("SERVO_ADAPT", tr("set measured Itarget"), tr("adaptive-step servo")),
            ("WAIT_CURRENT", tr("channel op val"), tr("wait for current cond.")),
            ("WAIT_TEMP", tr("sensor op val"), tr("wait for temperature cond.")),
            ("LOG", tr("text"), tr("message to the log")),
            ("ALL_OFF", "", tr("switches off all channels")),
            ("RELAY", tr("output ON|OFF"), tr("closes/opens a relay output")),
        ]

    def _seq_templates(self):
        tr = self.tr
        return {
            "SET": tr("SET <channel> <V> <I>"),
            "SETV": tr("SETV <channel> = <expr>"),
            "SETI": tr("SETI <channel> = <expr>"),
            "ON": tr("ON <channel>"),
            "OFF": tr("OFF <channel>"),
            "WAIT": tr("WAIT <s>"),
            "RAMP": tr("RAMP <channel> <Vend> <duration>"),
            "SERVO_LIN": tr("SERVO_LIN <set> <measured> <Itarget> step=0.02 tol=0.01"),
            "SERVO_ADAPT": tr("SERVO_ADAPT <set> <measured> <Itarget> step=0.5 tol=0.01"),
            "WAIT_CURRENT": tr("WAIT_CURRENT <channel> >= <val> timeout=10"),
            "WAIT_TEMP": tr("WAIT_TEMP <sensor> <= <val> timeout=10"),
            "LOG": tr("LOG <text>"),
            "ALL_OFF": "ALL_OFF",
            "RELAY": tr("RELAY <output> ON"),
        }

    def _seq_help_html(self, labels, sensors, relays=()) -> str:
        C = theme.pair("syntax.command")[1]
        K = theme.pair("syntax.key")[1]
        G = theme.pair("syntax.label")[1]
        cm = theme.pair("syntax.comment")[1]
        # Chaînes traduites extraites hors des f-strings : un self.tr(...) imbriqué
        # dans une f-string échappe à lupdate et ne serait jamais traduit.
        t_click = self.tr("Click a command to insert it at the cursor.")
        t_keys = self.tr("SERVO keys: step, min, max, tol, timeout, settle, invert "
                         "(+ damping for ADAPT)<br>op: &lt; &lt;= &gt; &gt;= == !=<br>"
                         "# or // : comment")
        t_channels = self.tr("Channels &amp; groups")
        t_sensors = self.tr("Sensors")
        t_relays = self.tr("Relays")
        out = ["<div style='font-family:sans-serif; font-size:12px'>",
               f"<p style='color:{cm}'>{t_click}</p>",
               "<table cellspacing='0' cellpadding='2'>"]
        for cmd, args, desc in self._seq_rows():
            out.append(
                "<tr>"
                f"<td><a href='ins:{cmd}' style='color:{C}; font-weight:bold; "
                f"text-decoration:none'>{cmd}</a>&nbsp;</td>"
                f"<td style='color:{K}'><code>{args}</code>&nbsp;&nbsp;</td>"
                f"<td style='color:{cm}'>{desc}</td></tr>")
        out.append("</table>")
        out.append(f"<p style='color:{cm}'>{t_keys}</p>")
        out.append(f"<p><b>{t_channels}</b><br>"
                   f"<span style='color:{G}'>{', '.join(labels)}</span></p>")
        if sensors:
            out.append(f"<p><b>{t_sensors}</b><br>"
                       f"<span style='color:{G}'>{', '.join(sensors)}</span></p>")
        if relays:
            out.append(f"<p><b>{t_relays}</b><br>"
                       f"<span style='color:{G}'>{', '.join(relays)}</span></p>")
        out.append("</div>")
        return "".join(out)

    def _build_seq_editor_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget(); v = QtWidgets.QVBoxLayout(w)
        bar = QtWidgets.QHBoxLayout()
        for txt, fn in [(self.tr("New"), self._seq_new), (self.tr("Open…"), self._seq_open),
                        (self.tr("Save"), self._seq_save), (self.tr("Save as…"), self._seq_save_as),
                        (self.tr("Check"), self._seq_verify)]:
            b = QtWidgets.QPushButton(txt); b.clicked.connect(fn); bar.addWidget(b)
        run = QtWidgets.QPushButton(self.tr("▶ Load & run"))
        run.setStyleSheet(theme.style("button.start", "font-weight:bold;"))
        run.clicked.connect(self._seq_load_and_run); bar.addWidget(run)
        self._seq_run_btn = run
        self.seq_edit_path = QtWidgets.QLabel(""); self.seq_edit_path.setStyleSheet(theme.style("text.muted"))
        bar.addWidget(self.seq_edit_path); bar.addStretch(1)
        v.addLayout(bar)

        labels = list(self.ctrl.cfg.all_labels)
        sensors = list(self.ctrl.cfg.temperatures)

        split = QtWidgets.QSplitter()
        self.seq_editor = CompletingPlainTextEdit()
        mono = QtGui.QFont("Monospace"); mono.setStyleHint(QtGui.QFont.Monospace)
        self.seq_editor.setFont(mono)
        self.seq_editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.seq_editor.setTabStopDistance(4 * self.seq_editor.fontMetrics().horizontalAdvance(" "))
        self._seq_highlighter = SeqHighlighter(self.seq_editor.document(), labels, sensors)
        self.seq_editor.cursorPositionChanged.connect(self._update_editor_selections)
        # Lint en direct : validation debounced (300 ms) au fil de la frappe -> statut
        # ✓/✗ et soulignage de la ligne fautive, sans voler le bouton « Vérifier ».
        self._seq_error_line = 0
        self._lint_timer = QtCore.QTimer(self)
        self._lint_timer.setSingleShot(True)
        self._lint_timer.setInterval(300)
        self._lint_timer.timeout.connect(self._seq_lint)
        self.seq_editor.textChanged.connect(self._lint_timer.start)
        # Auto-complétion : commandes + voies/groupes + capteurs.
        self.seq_editor.set_completer(QtWidgets.QCompleter(self.seq_editor))
        self.seq_editor.set_completion_words(
            list(SeqHighlighter.CMDS) + labels + sensors + list(self.ctrl.cfg.relay_labels))
        # Titre dynamique : ● si l'éditeur a des modifications non enregistrées.
        self.seq_editor.document().modificationChanged.connect(self._on_editor_modified)
        split.addWidget(self.seq_editor)

        help_box = QtWidgets.QTextBrowser()
        help_box.setOpenLinks(False)
        help_box.anchorClicked.connect(self._seq_insert_template)
        help_box.setHtml(self._seq_help_html(labels, sensors, list(self.ctrl.cfg.relay_labels)))
        help_box.setMaximumWidth(420)
        self._seq_help_box = help_box
        split.addWidget(help_box)
        split.setStretchFactor(0, 1); split.setStretchFactor(1, 0)
        v.addWidget(split, 1)

        self.seq_edit_status = QtWidgets.QLabel("")
        v.addWidget(self.seq_edit_status)

        last = self._settings.value("last_seq", "")
        default = Path(last) if last and Path(last).exists() else Path("sequences/demo.seq")
        if default.exists():
            try:
                self.seq_editor.setPlainText(read_text_tolerant(default))
                self.seq_edit_path.setText(str(default))
            except OSError:
                pass   # fichier illisible au démarrage : éditeur vierge, pas de crash
        self.seq_editor.document().setModified(False)
        self._update_editor_selections()
        self._update_title()
        return w

    def _update_editor_selections(self) -> None:
        """Surligne la ligne du curseur, et (si une séquence lancée depuis l'éditeur
        s'exécute) la ligne en cours d'exécution."""
        sels = []
        cur_line = QtWidgets.QTextEdit.ExtraSelection()
        col = self.palette().color(QtGui.QPalette.Highlight); col.setAlpha(30)
        cur_line.format.setBackground(col)
        cur_line.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
        c = self.seq_editor.textCursor(); c.clearSelection()
        cur_line.cursor = c
        sels.append(cur_line)

        if self._seq_from_editor and self._seq_run_line > 0:
            doc = self.seq_editor.document()
            block = doc.findBlockByNumber(self._seq_run_line - 1)
            if block.isValid():
                run = QtWidgets.QTextEdit.ExtraSelection()
                run_bg, run_fg = theme.pair("editor.runline")
                run.format.setBackground(QtGui.QColor(run_bg))
                run.format.setForeground(QtGui.QColor(run_fg))
                run.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
                rc = QtGui.QTextCursor(block)
                run.cursor = rc
                sels.append(run)
        # Ligne fautive (lint en direct) : soulignage vague rouge.
        err = getattr(self, "_seq_error_line", 0)
        if err > 0:
            block = self.seq_editor.document().findBlockByNumber(err - 1)
            if block.isValid():
                e = QtWidgets.QTextEdit.ExtraSelection()
                e.format.setUnderlineStyle(QtGui.QTextCharFormat.SpellCheckUnderline)
                e.format.setUnderlineColor(QtGui.QColor(0xE3, 0x49, 0x48))
                ec = QtGui.QTextCursor(block)
                ec.select(QtGui.QTextCursor.LineUnderCursor)
                e.cursor = ec
                sels.append(e)
        self.seq_editor.setExtraSelections(sels)

    def _seq_insert_template(self, url) -> None:
        s = url.toString()
        if not s.startswith("ins:"):
            return
        snippet = self._seq_templates().get(s[4:], s[4:])
        cur = self.seq_editor.textCursor()
        if cur.block().text().strip():       # ligne non vide -> nouvelle ligne
            cur.movePosition(QtGui.QTextCursor.EndOfLine)
            cur.insertText("\n" + snippet)
        else:
            cur.insertText(snippet)
        self.seq_editor.setFocus()

    def _seq_new(self) -> None:
        self.seq_editor.clear(); self.seq_edit_path.setText("")
        self.seq_editor.document().setModified(False)
        self.seq_edit_status.setText(self.tr("New sequence."))
        self.seq_edit_status.setStyleSheet(theme.style("text.muted"))
        self._update_title()

    def _seq_open(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.tr("Open a sequence"), self._dialog_dir(), self.tr("Sequence (*.seq *.txt);;All (*)"))
        if not path:
            return
        try:
            text = read_text_tolerant(path)
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, self.tr("Open a sequence"), str(exc))
            return
        self.seq_editor.setPlainText(text)
        self.seq_edit_path.setText(path)
        self.seq_editor.document().setModified(False)
        self._settings.setValue("last_seq", path)
        self._remember_dir(path)
        self.seq_edit_status.setText(self.tr("Opened: {}").format(Path(path).name))
        self.seq_edit_status.setStyleSheet(theme.style("text.muted"))
        self._update_title()

    def _seq_save(self) -> bool:
        """Enregistre la séquence. Retourne True si elle a réellement été écrite,
        False si l'utilisateur a annulé « Enregistrer sous… » ou en cas d'erreur
        d'écriture (le closeEvent s'en sert pour ne pas fermer sur perte de données)."""
        p = self.seq_edit_path.text().strip()
        if not p:
            return self._seq_save_as()
        try:
            Path(p).write_text(self.seq_editor.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, self.tr("Save the sequence"), str(exc))
            return False
        self.seq_editor.document().setModified(False)
        self._settings.setValue("last_seq", p)
        self.seq_edit_status.setText(self.tr("Saved: {}").format(Path(p).name))
        self.seq_edit_status.setStyleSheet(theme.style("text.ok"))
        self._update_title()
        return True

    def _seq_save_as(self) -> bool:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, self.tr("Save the sequence"), self._dialog_dir(), self.tr("Sequence (*.seq);;All (*)"))
        if not path:
            return False
        self.seq_edit_path.setText(path)
        self._remember_dir(path)
        return self._seq_save()

    def _seq_parse_editor(self):
        return parse_sequence(self.seq_editor.toPlainText(),
                              set(self.ctrl.cfg.all_labels), set(self.ctrl.cfg.temperatures),
                              set(self.ctrl.cfg.relay_labels))

    def _seq_lint(self) -> None:
        """Validation en direct (debounce 300 ms) : statut ✓/✗ et soulignage de la
        ligne fautive. Le n° de ligne est extrait du message (« Ligne N: … »)."""
        try:
            actions = self._seq_parse_editor()
        except (SequenceError, ValueError) as exc:
            # Message is localized ("Line N" in English, "Ligne N" in French).
            m = re.search(r"(?:Line|Ligne)\s+(\d+)", str(exc))
            self._seq_error_line = int(m.group(1)) if m else 0
            self.seq_edit_status.setText(f"✗ {exc}")
            self.seq_edit_status.setStyleSheet(theme.style("text.error"))
        else:
            self._seq_error_line = 0
            dur = estimate_duration(actions)
            extra = self.tr(", ~{:.0f}s min").format(dur) if dur > 0 else ""
            self.seq_edit_status.setText(self.tr("✓ Valid sequence ({} actions{}).").format(len(actions), extra))
            self.seq_edit_status.setStyleSheet(theme.style("text.ok"))
        self._update_editor_selections()

    def _seq_verify(self) -> bool:
        try:
            actions = self._seq_parse_editor()
        except (SequenceError, ValueError) as exc:
            self.seq_edit_status.setText(f"✗ {exc}")
            self.seq_edit_status.setStyleSheet(theme.style("text.error"))
            return False
        dur = estimate_duration(actions)
        extra = self.tr(", ~{:.0f}s min").format(dur) if dur > 0 else ""
        self.seq_edit_status.setText(self.tr("✓ Valid sequence ({} actions{}).").format(len(actions), extra))
        self.seq_edit_status.setStyleSheet(theme.style("text.ok"))
        return True

    def _seq_load_and_run(self) -> None:
        if not self._seq_verify():
            return
        self._actions = self._seq_parse_editor()
        self._seq_text = self.seq_editor.toPlainText()
        self.tabs.setCurrentIndex(0)
        self._start_sequence(from_editor=True)
