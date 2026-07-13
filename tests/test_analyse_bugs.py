"""Régressions des bugs de l'analyse critique (2026-07-12) — B1 à B6 + mineurs.

Chaque test porte le numéro du constat pour la traçabilité.
"""

import json
import math
import threading
import time

import pytest

from alim_seq.config import load_config
from alim_seq.controller import Controller
from alim_seq.sequencer import _OPS, parse_sequence
from alim_seq.temperature import (NTCConverter, PTCConverter,
                                  ThermocoupleConverter, build_converter)


def _write(tmp_path, raw, name="cfg.json"):
    p = tmp_path / name
    p.write_text(json.dumps(raw), encoding="utf-8")
    return p


_BASE = {
    "simulate": True,
    "supplies": {"P": {"model": "HMP4040"}},
    "channels": {"A": {"supply": "P", "channel": 1}},
    "temperatures": {},
    "safety": {},
}


# --- B1 : thermocouple — détection de défaut -------------------------------------
def test_b1_tc_hors_plage_polynome_donne_nan():
    # Entrée flottante / collée à un rail : emf aberrante -> NaN (DÉFAUT), jamais
    # une température extravagante mais « numérique ».
    tc = ThermocoupleConverter(tc_type="K", cjc_c=25.0)
    assert math.isnan(tc.to_celsius(5.0))      # 5 V = ~5000 mV d'emf : absurde
    assert math.isnan(tc.to_celsius(-1.0))
    # Une mesure réaliste reste convertie normalement.
    assert 20.0 < tc.to_celsius(0.0) < 30.0    # ~soudure froide


def test_b1_tc_sans_bande_plausible_rejete(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["temperatures"] = {"T1": {"channel": "ai0", "warning": 60, "critical": 80,
                                  "converter": {"type": "thermocouple"}}}
    with pytest.raises(ValueError, match="valid_min"):
        load_config(_write(tmp_path, raw))
    # Avec la bande, la config passe.
    raw["temperatures"]["T1"]["valid_min"] = -20
    raw["temperatures"]["T1"]["valid_max"] = 150
    load_config(_write(tmp_path, raw, "ok.json"))


# --- B2 : paramètres de convertisseur aberrants rejetés à la VALIDATION ----------
def test_b2_ptc_alpha_zero_rejete_a_la_construction():
    with pytest.raises(ValueError, match="alpha"):
        PTCConverter(r_series=1000, v_ref=5, r0=100, t0=0, alpha=0.0)
    with pytest.raises(ValueError, match="beta"):
        NTCConverter(r_series=1000, v_ref=5, r0=10000, t0=25, beta=0.0)


def test_b2_convertisseur_invalide_rejete_au_chargement(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["temperatures"] = {"T1": {"channel": "ai0", "warning": 60, "critical": 80,
                                  "converter": {"type": "ptc", "r_series": 1000,
                                                "v_ref": 5, "r0": 100, "t0": 0,
                                                "alpha": 0.0}}}
    with pytest.raises(ValueError, match="convertisseur invalide"):
        load_config(_write(tmp_path, raw))
    # Clé manquante : détectée aussi dès la validation, plus à la 1re mesure.
    raw["temperatures"]["T1"]["converter"] = {"type": "ntc", "r_series": 1000}
    with pytest.raises(ValueError, match="convertisseur invalide"):
        load_config(_write(tmp_path, raw, "c2.json"))


# --- B3 : collision de dossiers d'essai ------------------------------------------
def test_b3_deux_essais_meme_seconde_dossiers_distincts(tmp_path):
    from alim_seq.essai import DossierEssai

    class FakeCtrl:
        class cfg:
            simulate = True
            source_path = None
        def add_log_listener(self, f): pass
        def remove_log_listener(self, f): pass
        _meas_period = 0.0
        _temp_period = 0.0

    import alim_seq.config as C
    orig = C.config_to_dict
    C.config_to_dict = lambda c: {}
    try:
        d1 = DossierEssai(FakeCtrl(), nom="x", base_dir=str(tmp_path))
        d2 = DossierEssai(FakeCtrl(), nom="x", base_dir=str(tmp_path))
        assert d1.path != d2.path
        assert d2.path.name.endswith("_2")
    finally:
        C.config_to_dict = orig


# --- B4 : opérateurs == et != acceptés et corrects --------------------------------
def test_b4_operateurs_egalite():
    assert _OPS["=="](1.0, 1.0) and not _OPS["=="](1.0, 1.1)
    assert _OPS["!="](1.0, 1.1) and not _OPS["!="](1.0, 1.0)
    # Et la validation de séquence les accepte (l'aide de l'éditeur les annonce).
    acts = parse_sequence("WAIT_CURRENT A != 0.5 timeout=1", {"A"}, set())
    assert acts[0].args[1] == "!="


# --- B5 : reconnexions concurrentes sérialisées -----------------------------------
def test_b5_reconnect_concurrent_refuse(tmp_path):
    cfg = load_config(_write(tmp_path, _BASE))
    c = Controller(cfg)
    assert c.connect()
    c.stop_polling()
    # Simule une reconnexion en cours : le verrou est tenu par un autre thread.
    assert c._reconnect_lock.acquire(blocking=False)
    try:
        assert c.reconnect() is False   # refusée, pas d'entrelacement
    finally:
        c._reconnect_lock.release()
    assert c.reconnect() is True        # à nouveau possible ensuite
    c.close()


# --- B6 : la boucle V/I ne se fige plus sur un verrou indisponible ----------------
def test_b6_meas_cycle_saute_l_instrument_verrouille(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["supplies"]["P2"] = {"model": "HMP4040"}
    raw["channels"]["B"] = {"supply": "P2", "channel": 1}
    cfg = load_config(_write(tmp_path, raw))
    c = Controller(cfg)
    assert c.connect()
    c.stop_polling()
    c.set_voltage("B", 3.0); c.set_current("B", 5.0); c.set_output("B", True)
    # Fige P : verrou tenu depuis un AUTRE thread (RLock réentrant — un appel VISA
    # suspendu le tient depuis le thread séquenceur, pas depuis la boucle de mesure).
    held = threading.Event()
    release = threading.Event()

    def holder():
        with c._instr_locks["P"]:
            held.set()
            release.wait(timeout=10)

    th = threading.Thread(target=holder, daemon=True)
    th.start()
    assert held.wait(timeout=2)
    try:
        t0 = time.monotonic()
        c._meas_cycle()
        elapsed = time.monotonic() - t0
        assert elapsed < 3.0            # timeout 1 s, pas un blocage infini
        # P2, elle, a bien été mesurée.
        assert c.snapshot().channels["B"].meas_voltage > 2.0
        assert c._meas_skip["P"] == 1
    finally:
        release.set()
        th.join(timeout=2)
    c._meas_cycle()
    assert c._meas_skip["P"] == 0       # rétabli après un cycle réussi
    c.close()


# --- Indicateur d'état périmé : snapshot.stale_labels --------------------------------
def test_snapshot_stale_labels(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["supplies"]["P2"] = {"model": "HMP4040"}
    raw["channels"]["B"] = {"supply": "P2", "channel": 1}
    c = Controller(load_config(_write(tmp_path, raw)))
    assert c.connect()
    c.stop_polling()
    held = threading.Event(); release = threading.Event()

    def holder():
        with c._instr_locks["P"]:
            held.set(); release.wait(timeout=10)

    th = threading.Thread(target=holder, daemon=True); th.start()
    assert held.wait(timeout=2)
    try:
        c._meas_cycle()
        snap = c.snapshot()
        assert "A" in snap.stale_labels        # voie de P (figée) -> périmée
        assert "B" not in snap.stale_labels     # voie de P2 -> à jour
    finally:
        release.set(); th.join(timeout=2)
    c._meas_cycle()
    assert c.snapshot().stale_labels == set()   # plus rien de périmé
    c.close()


# --- Mineur : cache d'état des relais (pas d'OFF fantôme) --------------------------
def test_relay_states_cache_si_verrou_occupe(tmp_path):
    raw = json.loads(json.dumps(_BASE))
    raw["instruments"] = {"RLY": {"driver": "MOCK-RELAY", "outputs": ["K1"]}}
    cfg = load_config(_write(tmp_path, raw))
    c = Controller(cfg)
    assert c.connect()
    c.stop_polling()
    c.set_relay("K1", True)
    assert c.relay_states() == {"K1": True}
    # Verrou du relais occupé : on ressert la dernière valeur connue, pas un vide.
    c._instr_locks["RLY"].acquire()
    try:
        assert c.relay_states() == {"K1": True}
    finally:
        c._instr_locks["RLY"].release()
    c.close()
