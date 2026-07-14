"""Lignes de tableau de l'onglet Contrôle : voies (ChannelRowQt) et températures."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..controller import FAULT, NA, Controller
from . import theme


class NoScrollDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    """QDoubleSpinBox durci pour la saisie de consignes de matériel réel :

    - la **molette** est ignorée sauf si le champ a le focus ET Ctrl est enfoncé
      (un coup de molette qui change une tension est un piège classique) ;
    - **Entrée** déclenche ``on_enter`` (= Appliquer) au lieu de simplement
      valider le champ.
    """

    def __init__(self, on_enter=None, parent=None):
        super().__init__(parent)
        self._on_enter = on_enter

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self.hasFocus() and (event.modifiers() & QtCore.Qt.ControlModifier):
            super().wheelEvent(event)
        else:
            event.ignore()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if (event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter)
                and self._on_enter is not None):
            self.interpretText()   # prend en compte la saisie en cours
            self._on_enter()
            return
        super().keyPressEvent(event)


class ChannelRowQt:
    """Une ligne de pilotage d'une voie, ajoutée à un QGridLayout."""

    @staticmethod
    def headers():
        return [QtCore.QCoreApplication.translate("ChannelRowQt", "Channel"),
                QtCore.QCoreApplication.translate("ChannelRowQt", "V setpoint"),
                QtCore.QCoreApplication.translate("ChannelRowQt", "I limit"), "",
                QtCore.QCoreApplication.translate("ChannelRowQt", "Output"),
                QtCore.QCoreApplication.translate("ChannelRowQt", "V measured"),
                QtCore.QCoreApplication.translate("ChannelRowQt", "I measured"),
                QtCore.QCoreApplication.translate("ChannelRowQt", "Mode")]

    def __init__(self, grid: QtWidgets.QGridLayout, row: int, label: str, ctrl: Controller):
        self.label = label
        self.ctrl = ctrl
        sp = ctrl.get_setpoint(label)

        name = QtWidgets.QLabel(label)
        # Gras via la POLICE, jamais via un stylesheet : un widget stylé fige la
        # résolution de palette et deviendrait illisible après un changement de thème.
        f = name.font(); f.setBold(True); name.setFont(f)
        grid.addWidget(name, row, 0)

        # Consignes bornées par la config (le clamp du contrôleur reste l'autorité).
        vlo, vhi = ctrl.voltage_bounds(label)
        ilo, ihi = ctrl.current_bounds(label)
        self.v_set = NoScrollDoubleSpinBox(on_enter=self._apply)
        self.v_set.setDecimals(3); self.v_set.setSingleStep(0.1)
        self.v_set.setRange(vlo, vhi); self.v_set.setSuffix(" V")
        self.v_set.setValue(max(vlo, min(sp.set_voltage, vhi)))
        self.i_set = NoScrollDoubleSpinBox(on_enter=self._apply)
        self.i_set.setDecimals(3); self.i_set.setSingleStep(0.01)
        self.i_set.setRange(ilo, ihi); self.i_set.setSuffix(" A")
        self.i_set.setValue(max(ilo, min(sp.set_current, ihi)))
        # Locale française : la virgule décimale est acceptée (le point l'est aussi).
        fr = QtCore.QLocale(QtCore.QLocale.French)
        for w in (self.v_set, self.i_set):
            w.setMaximumWidth(110)
            w.setKeyboardTracking(False)   # ne pas émettre à chaque frappe
            w.setLocale(fr)
        grid.addWidget(self.v_set, row, 1)
        grid.addWidget(self.i_set, row, 2)

        self.apply_btn = QtWidgets.QPushButton(QtCore.QCoreApplication.translate("ChannelRowQt", "Apply"))
        self.apply_btn.setMaximumWidth(110)
        self.apply_btn.clicked.connect(self._apply)
        grid.addWidget(self.apply_btn, row, 3)

        self.btn_out = QtWidgets.QPushButton(QtCore.QCoreApplication.translate("ChannelRowQt", "OFF"))
        self.btn_out.setMaximumWidth(70)
        self.btn_out.clicked.connect(self._toggle)
        grid.addWidget(self.btn_out, row, 4)

        self.v_meas = QtWidgets.QLabel("-- V")
        self.i_meas = QtWidgets.QLabel("-- A")
        self.mode = QtWidgets.QLabel("")
        for w in (self.v_meas, self.i_meas):
            w.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            w.setMinimumWidth(80)
        grid.addWidget(self.v_meas, row, 5)
        grid.addWidget(self.i_meas, row, 6)
        grid.addWidget(self.mode, row, 7)

        # États mémorisés (anti-churn) : on ne re-pose la palette « en attente » et
        # le gras du bouton Appliquer que sur transition (voir update()).
        self._v_pending = False
        self._i_pending = False
        self._apply_bold = False

        # Armement en deux temps du ON en matériel réel : 1er clic = « armer »,
        # 2e clic (sous délai) = allumer. Aucun frein en simulation ; Maj+clic force.
        self._armed = False
        self._disarm_timer = QtCore.QTimer(self.btn_out)
        self._disarm_timer.setSingleShot(True)
        self._disarm_timer.setInterval(3000)
        self._disarm_timer.timeout.connect(self._disarm)

    def _set_pending(self, spin: QtWidgets.QDoubleSpinBox, pending: bool) -> None:
        """Met (ou retire) la mise en évidence « consigne modifiée non appliquée »
        via une PALETTE locale — jamais un stylesheet (préserve les flèches natives)."""
        if pending:
            bg, fg = theme.pair("pending")
            pal = QtGui.QPalette()
            pal.setColor(QtGui.QPalette.Base, QtGui.QColor(bg))
            pal.setColor(QtGui.QPalette.Text, QtGui.QColor(fg))
            spin.setPalette(pal)
        else:
            spin.setPalette(QtGui.QPalette())   # restaure la palette héritée

    def reset_pending_cache(self) -> None:
        """Invalide les états mémorisés (appelé au changement de thème) : la prochaine
        mise à jour ré-applique la palette « en attente » avec les couleurs du thème."""
        self._v_pending = None
        self._i_pending = None
        self._apply_bold = None

    def _apply(self) -> None:
        # Les spinboxes garantissent déjà des valeurs numériques bornées.
        self.ctrl.set_voltage(self.label, self.v_set.value())
        self.ctrl.set_current(self.label, self.i_set.value())

    def _toggle(self) -> None:
        sp = self.ctrl.get_setpoint(self.label)
        if sp.output:
            self._disarm()
            self.ctrl.set_output(self.label, False)   # extinction : toujours immédiate
            return
        shift = bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier)
        if self.ctrl.cfg.simulate or shift or self._armed:
            self._disarm()
            self.ctrl.set_output(self.label, True)
            return
        # Matériel réel, 1er clic : on ARME (filet contre le clic malheureux à 32 V).
        self._armed = True
        self._disarm_timer.start()
        self.btn_out.setText(QtCore.QCoreApplication.translate("ChannelRowQt", "⚠ Arm?"))
        self.btn_out.setStyleSheet(theme.style("status.warning", "font-weight:bold;"))

    def _disarm(self) -> None:
        self._armed = False
        self._disarm_timer.stop()

    def set_controls_enabled(self, on: bool) -> None:
        """Active/désactive les commandes matérielles de la ligne (pendant une
        opération VISA/NI déportée : évite d'empiler des ordres sur du matériel
        en cours de (re)connexion)."""
        self.apply_btn.setEnabled(on)
        self.btn_out.setEnabled(on)

    def update(self, view, tripped: bool = False, hw_enabled: bool = True,
               stale: bool = False) -> None:
        self.v_meas.setText(f"{view.meas_voltage:6.3f} V")
        self.i_meas.setText(f"{view.meas_current:6.3f} A")
        # Mesures périmées (instrument sauté au dernier cycle) : on GRISE les valeurs
        # V/I et on l'annonce, plutôt que de laisser croire à une mesure vivante.
        muted = theme.style("text.muted", fg_only=True) if stale else ""
        self.v_meas.setStyleSheet(muted)
        self.i_meas.setStyleSheet(muted)
        # Bouton de sortie : « ⚠ Armer ? » a la priorité (armement 2 temps en cours).
        if self._armed and not view.output:
            self.btn_out.setText(QtCore.QCoreApplication.translate("ChannelRowQt", "⚠ Arm?"))
            self.btn_out.setStyleSheet(theme.style("status.warning", "font-weight:bold;"))
        elif view.output:
            self.btn_out.setText(QtCore.QCoreApplication.translate("ChannelRowQt", "ON"))
            self.btn_out.setStyleSheet(theme.style("button.on", "font-weight:bold;"))
        else:
            self.btn_out.setText(QtCore.QCoreApplication.translate("ChannelRowQt", "OFF"))
            self.btn_out.setStyleSheet(theme.style("button.off"))
        if stale:
            self.mode.setText(QtCore.QCoreApplication.translate("ChannelRowQt", "⏱ frozen"))
            self.mode.setStyleSheet(theme.style("text.muted", fg_only=True))
        elif view.faults:
            self.mode.setText("/".join(view.faults))
            self.mode.setStyleSheet(theme.style("status.fault", "font-weight:bold;", fg_only=True))
        elif view.mode == "CC":
            self.mode.setText("CC")
            self.mode.setStyleSheet(theme.style("text.error", "font-weight:bold;"))
        elif view.mode == "CV":
            self.mode.setText("CV"); self.mode.setStyleSheet(theme.style("text.ok"))
        else:
            self.mode.setText("")

        # État « modifié non appliqué » : consigne saisie ≠ consigne active -> fond
        # du jeton `pending` + bouton Appliquer en gras. On n'écrit JAMAIS dans le
        # spinbox pendant que l'utilisateur édite (l'IHM ne réinjecte pas les consignes).
        # La mise en évidence passe par une PALETTE locale (pas un stylesheet) : le
        # QSS avec background-color casse le rendu natif des flèches du spinbox et
        # n'adapte pas la couleur du texte. On ne touche la palette (et le gras) QUE
        # sur transition, pour ne pas re-polir 5×/s pendant la saisie.
        eps = 5e-4
        v_pending = abs(self.v_set.value() - view.set_voltage) > eps
        i_pending = abs(self.i_set.value() - view.set_current) > eps
        if v_pending != self._v_pending:
            self._set_pending(self.v_set, v_pending); self._v_pending = v_pending
        if i_pending != self._i_pending:
            self._set_pending(self.i_set, i_pending); self._i_pending = i_pending
        bold = v_pending or i_pending
        if bold != self._apply_bold:
            f = self.apply_btn.font(); f.setBold(bold); self.apply_btn.setFont(f)
            self._apply_bold = bold

        # Commandes désactivées pendant une opération matérielle ; sur trip,
        # l'allumage est refusé par le contrôleur : feedback immédiat.
        self.apply_btn.setEnabled(hw_enabled)
        self.btn_out.setEnabled(hw_enabled and not (tripped and not view.output))


class RelayRowQt:
    """Une ligne de pilotage d'une sortie de relais, ajoutée à un QGridLayout."""

    @staticmethod
    def headers():
        return [QtCore.QCoreApplication.translate("RelayRowQt", "Output"),
                QtCore.QCoreApplication.translate("RelayRowQt", "State"), ""]

    def __init__(self, grid: QtWidgets.QGridLayout, row: int, label: str, ctrl: Controller):
        self.label = label
        self.ctrl = ctrl

        name = QtWidgets.QLabel(label)
        f = name.font(); f.setBold(True); name.setFont(f)   # gras via police (cf. supra)
        grid.addWidget(name, row, 0)

        self.state = QtWidgets.QLabel("--")
        self.state.setMinimumWidth(80)
        grid.addWidget(self.state, row, 1)

        self.btn = QtWidgets.QPushButton(QtCore.QCoreApplication.translate("RelayRowQt", "OFF"))
        self.btn.setMaximumWidth(90)
        self.btn.clicked.connect(self._toggle)
        grid.addWidget(self.btn, row, 2)

    def _toggle(self) -> None:
        cur = bool(self.ctrl.relay_state(self.label))
        self.ctrl.set_relay(self.label, not cur)

    def set_controls_enabled(self, on: bool) -> None:
        self.btn.setEnabled(on)

    def update(self, on: bool, tripped: bool = False, hw_enabled: bool = True) -> None:
        if on:
            self.state.setText(QtCore.QCoreApplication.translate("RelayRowQt", "closed (ON)"))
            self.state.setStyleSheet(theme.style("text.ok", fg_only=True))
            self.btn.setText(QtCore.QCoreApplication.translate("RelayRowQt", "ON"))
            self.btn.setStyleSheet(theme.style("button.on", "font-weight:bold;"))
        else:
            self.state.setText(QtCore.QCoreApplication.translate("RelayRowQt", "open (OFF)"))
            self.state.setStyleSheet(theme.style("text.muted", fg_only=True))
            self.btn.setText(QtCore.QCoreApplication.translate("RelayRowQt", "OFF"))
            self.btn.setStyleSheet(theme.style("button.off"))
        # Fermer un relais est refusé tant que la sécurité est armée : feedback immédiat.
        self.btn.setEnabled(hw_enabled and not (tripped and not on))


class TempRowQt:
    def __init__(self, grid: QtWidgets.QGridLayout, row: int, name: str,
                 warning: float, critical: float):
        nm = QtWidgets.QLabel(name)
        f = nm.font(); f.setBold(True); nm.setFont(f)   # gras via police (cf. supra)
        grid.addWidget(nm, row, 0)
        self.value = QtWidgets.QLabel("-- °C")
        self.value.setAlignment(QtCore.Qt.AlignCenter)
        f = self.value.font(); f.setPointSize(f.pointSize() + 2); f.setBold(True)
        self.value.setFont(f)
        # Aligné (pas étiré) dans la cellule : le fond de statut colore une pastille
        # ajustée au texte, pas toute la colonne (évite un gros bloc gris à vide).
        grid.addWidget(self.value, row, 1, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        grid.addWidget(QtWidgets.QLabel(f"⚠ {warning:.0f}   ⛔ {critical:.0f} °C"), row, 2)

    def update(self, temp: float, level: str) -> None:
        if level == NA:
            text = QtCore.QCoreApplication.translate("TempRowQt", "pending")
        elif level == FAULT:
            text = QtCore.QCoreApplication.translate("TempRowQt", "FAULT")
        elif temp != temp:  # NaN
            text = "-- °C"
        else:
            text = f"{temp:6.1f} °C"
        self.value.setText(text)
        self.value.setStyleSheet(theme.style(
            theme.level_token(level), "font-weight:bold; padding:1px 8px; border-radius:3px;"))