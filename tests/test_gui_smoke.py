"""Smokes de l'IHM Qt (offscreen) : construction, onglets, rafraîchissement et
interactions clés. Filet minimal sur ~3 600 lignes de gui_qt/ jusqu'ici sans test.

On n'exécute PAS de boucle d'événements : les QTimer ne se déclenchent pas, on
pilote `_refresh()` et les handlers à la main.
"""

import json
import os

import pytest

# L'IHM Qt exige un backend d'affichage : offscreen avant tout import PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6 import QtWidgets  # noqa: E402

from alim_seq.config import load_config  # noqa: E402
from alim_seq.controller import Controller  # noqa: E402


_RAW = {
    "simulate": True,
    "supplies": {"P": {"model": "HMP4040"}},
    "instruments": {"RLY": {"driver": "MOCK-RELAY", "outputs": ["K1"]}},
    "channels": {
        "CH1": {"supply": "P", "channel": 1, "max_voltage": 20, "max_current": 2},
        "CH2": {"supply": "P", "channel": 2, "max_voltage": 20, "max_current": 2},
    },
    "temperatures": {
        "T1": {"channel": "ai0", "warning": 60, "critical": 80,
               "converter": {"type": "identity"}},
    },
    "simulation": {
        "loads": {"CH1": 10.0, "CH2": 8.0},
        "couplings": [{"gate": "CH1", "drains": ["CH2"], "gm": 0.01,
                       "vth": 1.0, "imax": 0.5}],
    },
    "safety": {},
}


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def gui(qapp, tmp_path):
    from alim_seq.gui_qt.main_window import AlimSeqQtGUI
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(_RAW), encoding="utf-8")
    ctrl = Controller(load_config(p))
    assert ctrl.connect()
    ctrl.stop_polling()          # déterminisme : pas de threads de fond
    w = AlimSeqQtGUI(ctrl)
    yield w
    ctrl.close()


def test_gui_construit_tous_les_onglets(gui):
    titres = [gui.tabs.tabText(i) for i in range(gui.tabs.count())]
    joined = " ".join(titres)
    for attendu in ("Control", "Configuration", "Sequence editor", "Chart", "Simulation"):
        assert attendu in joined, (attendu, titres)


def test_gui_refresh_repete_sans_exception(gui):
    for _ in range(5):
        gui._refresh()          # ne doit jamais lever


def test_gui_pilotage_voie_et_relais(gui):
    gui.ctrl.set_voltage("CH1", 5.0)
    gui.ctrl.set_output("CH1", True)
    gui._refresh()
    assert gui.rows["CH1"].btn_out.text() == "ON"
    gui.ctrl.set_relay("K1", True)
    gui._refresh()
    assert gui.relay_rows["K1"].btn.text() == "ON"


def test_gui_marqueur_sans_dialogue(gui, monkeypatch):
    # _add_marker ouvre un QInputDialog bloquant : on le neutralise.
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("touché le condo", True)))
    gui._add_marker()
    assert any("📌 touché le condo" in l for l in gui.ctrl._logs)


def test_gui_lint_souligne_ligne_fautive(gui):
    gui.seq_editor.setPlainText("ON CH1\nON NOPE\nWAIT 1")
    gui._seq_lint()
    assert gui._seq_error_line == 2
    gui.seq_editor.setPlainText("ON CH1\nWAIT 1\nOFF CH1")
    gui._seq_lint()
    assert gui._seq_error_line == 0


def test_gui_graphe_change_de_mode(gui):
    gui.plot.set_mode("current")
    gui.plot.push({"T1": 25.0}, {"T1": "OK"}, {"CH1": (5.0, 0.5), "CH2": (0.0, 0.0)})
    gui._refresh()
    assert gui.plot.mode == "current"


def test_gui_reglage_simulation_en_direct(gui):
    gui._sim_load_spins["CH1"].setValue(4.0)
    assert gui.ctrl.sim_params()["loads"]["CH1"] == 4.0


def test_replay_charge_un_essai(qapp, tmp_path):
    """Relecture d'essai : les courbes du CSV sont chargées dans la vue statique,
    la bascule de grandeur fonctionne, et le rendu ne lève pas."""
    from alim_seq.gui_qt.replay import EssaiReplayView
    d = tmp_path / "essai1"; d.mkdir()
    (d / "mesures.csv").write_text(
        "t_s,T1_C,CH1_Vmeas,CH1_Imeas\n0.0,25.0,5.0,0.5\n1.0,26.0,5.0,0.6\n",
        encoding="utf-8")
    view = EssaiReplayView(d)
    assert view.sensors == ["T1"]
    assert "CH1" in view._channels
    assert len(view._series["current"]["CH1"]) == 2
    assert view.mode == "temp"                 # capteur présent -> démarre en °C
    view.resize(400, 300)
    assert not view.grab().isNull()            # paintEvent sans exception
    view.set_mode("current"); assert not view.grab().isNull()

    # Essai sans capteur -> démarre en « Courants ».
    d2 = tmp_path / "essai2"; d2.mkdir()
    (d2 / "mesures.csv").write_text(
        "t_s,CH1_Vmeas,CH1_Imeas\n0.0,3.0,0.2\n", encoding="utf-8")
    v2 = EssaiReplayView(d2)
    assert v2.sensors == [] and v2.mode == "current"


def test_config_wizard_genere_config(qapp, tmp_path):
    """L'assistant produit des configurations valides (simulation et scan matériel)."""
    from alim_seq.gui_qt.config_wizard import ConfigWizard, _sim_config
    # Voie simulation.
    ps = tmp_path / "sim.json"
    ps.write_text(json.dumps(_sim_config()), encoding="utf-8")
    assert load_config(ps).channels                     # config sim valide

    # Voie scan : on injecte un résultat, on génère.
    wiz = ConfigWizard(None)
    wiz._scan_done([{"resource": "TCPIP0::10.0.0.5::5025::SOCKET",
                     "idn": "Rohde&Schwarz,HMP4040,x"}])
    assert wiz.table.rowCount() == 1 and wiz.btn_generate.isEnabled()
    wiz._generate()
    raw = wiz.result_config
    assert raw["simulate"] is False
    assert list(raw["supplies"]) == ["PSU1"]
    assert len([c for c in raw["channels"] if c.startswith("PSU1_")]) == 4  # HMP4040
    pg = tmp_path / "gen.json"
    pg.write_text(json.dumps(raw), encoding="utf-8")
    assert load_config(pg).supplies["PSU1"]["model"] == "HMP4040"   # se charge


def test_config_wizard_adresse_manuelle(qapp, tmp_path):
    """Ajout manuel d'une adresse (socket LAN non découvrable) : succès testé et
    échec ajouté sur confirmation ; les adresses sont préservées dans la config."""
    from alim_seq.gui_qt.config_wizard import ConfigWizard
    wiz = ConfigWizard(None)
    wiz._manual_ok("TCPIP0::192.168.0.11::5025::SOCKET", "R&S,HMP4040,1,1")
    assert wiz.table.rowCount() == 1 and wiz.btn_generate.isEnabled()
    wiz._generate()
    addrs = [s["resource"] for s in wiz.result_config["supplies"].values()]
    assert "TCPIP0::192.168.0.11::5025::SOCKET" in addrs
    p = tmp_path / "m.json"
    p.write_text(json.dumps(wiz.result_config), encoding="utf-8")
    assert load_config(p).simulate is False


def test_armement_deux_temps(gui):
    """En simulation, ON est direct ; en matériel réel, 1er clic = armer, 2e = ON."""
    row = gui.rows["CH1"]
    row._toggle()
    assert gui.ctrl.get_setpoint("CH1").output is True      # sim -> ON direct
    row._toggle()
    assert gui.ctrl.get_setpoint("CH1").output is False     # OFF immédiat
    gui.ctrl.cfg.simulate = False                            # force le chemin réel
    try:
        row._toggle()                                       # 1er clic -> armer
        assert row._armed and gui.ctrl.get_setpoint("CH1").output is False
        row._toggle()                                       # 2e clic -> ON
        assert not row._armed and gui.ctrl.get_setpoint("CH1").output is True
    finally:
        gui.ctrl.cfg.simulate = True


def test_compare_deux_essais(qapp, tmp_path):
    """Comparaison : les séries des deux essais sont fusionnées (préfixes A·/B·) et
    rendues dans les trois modes."""
    from alim_seq.gui_qt.replay import EssaiCompareView
    a = tmp_path / "A"; a.mkdir(); b = tmp_path / "B"; b.mkdir()
    (a / "mesures.csv").write_text(
        "t_s,T1_C,CH1_Vmeas,CH1_Imeas\n0,25,5,0.5\n1,30,5,0.55\n", encoding="utf-8")
    (b / "mesures.csv").write_text(
        "t_s,T1_C,CH1_Vmeas,CH1_Imeas\n0,25,5,0.7\n1,34,5,0.8\n", encoding="utf-8")
    view = EssaiCompareView(a, b)
    assert set(view.sensors) == {"A·T1", "B·T1"}
    assert set(view._channels) == {"A·CH1", "B·CH1"}
    assert len(view._series["current"]["B·CH1"]) == 2
    view.resize(400, 300)
    for mode in ("temp", "current", "voltage"):
        view.set_mode(mode)
        assert not view.grab().isNull()


def test_graphe_visible_sans_capteur(qapp, tmp_path):
    """Régression : l'onglet Graphe (qui trace aussi V/I) doit exister et fonctionner
    même sans capteur de température déclaré."""
    from alim_seq.gui_qt.main_window import AlimSeqQtGUI
    raw = dict(_RAW, temperatures={})   # aucun capteur
    p = tmp_path / "c.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    ctrl = Controller(load_config(p))
    assert ctrl.connect()
    ctrl.stop_polling()
    w = AlimSeqQtGUI(ctrl)
    try:
        titres = " ".join(w.tabs.tabText(i) for i in range(w.tabs.count()))
        assert "Chart" in titres
        assert w.plot is not None and w.plot.mode == "current"  # pas 'temp' (rien à tracer)
        ctrl.set_voltage("CH1", 5.0); ctrl.set_output("CH1", True)
        w._refresh()
        assert len(w.plot._series["current"]["CH1"]) >= 1
    finally:
        ctrl.close()
