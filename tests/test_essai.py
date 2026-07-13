"""Dossier d'essai autonome : structure, empreintes, issue, journal, robustesse."""

import hashlib
import json

import pytest

from alim_seq.essai import (ISSUE_ARRET_UTILISATEUR, ISSUE_DECLENCHEMENT,
                            ISSUE_TERMINE, safe_folder_name)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_a_bit(ctrl, cycles=3):
    ctrl.set_output("VLOAD", True)
    ctrl._temp_cycle()
    for _ in range(cycles):
        ctrl._meas_cycle()


def test_dossier_structure_et_empreintes(ctrl, tmp_path, monkeypatch):
    """Un enregistrement en simulation produit un dossier autonome complet, et
    l'empreinte inscrite correspond au contenu réellement archivé."""
    monkeypatch.chdir(tmp_path)
    path = ctrl.start_recording(nom="Essai démo", operateur="Alice")
    essai = ctrl.essai
    _record_a_bit(ctrl)
    ctrl.stop_recording()

    d = essai.path
    assert d.parent.name == "essais"
    assert (d / "mesures.csv").exists()
    assert (d / "config.json").exists()
    assert (d / "journal.log").exists()
    assert (d / "essai.json").exists()
    # Pas de séquence exécutée -> pas de sequence.seq.
    assert not (d / "sequence.seq").exists()
    assert path == d / "mesures.csv"

    meta = json.loads((d / "essai.json").read_text(encoding="utf-8"))
    assert meta["mode"] == "simulation"
    assert meta["nom"] == "Essai démo" and meta["operateur"] == "Alice"
    assert meta["version"]
    assert meta["debut"] and meta["fin"]
    # Empreinte SHA-256 exacte du config.json archivé.
    assert meta["config_sha256"] == _sha(d / "config.json")
    assert meta["issue"]["issue"] == ISSUE_TERMINE

    # La config archivée (mémoire sérialisée) est un JSON rechargeable.
    json.loads((d / "config.json").read_text(encoding="utf-8"))

    # Le CSV comporte au moins une ligne de mesures (plus l'en-tête).
    rows = (d / "mesures.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) >= 2


def test_config_copie_a_lidentique_depuis_fichier(ctrl, tmp_path, monkeypatch):
    """Si la config vient d'un fichier, config.json en est la copie octet pour
    octet et l'empreinte porte sur ce contenu d'origine."""
    src = tmp_path / "profil.json"
    src.write_bytes(json.dumps({"nom": "peu importe"}).encode("utf-8"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ctrl.cfg, "source_path", src)

    ctrl.start_recording()
    essai = ctrl.essai
    _record_a_bit(ctrl, cycles=1)
    ctrl.stop_recording()

    archived = essai.path / "config.json"
    assert archived.read_bytes() == src.read_bytes()
    meta = json.loads((essai.path / "essai.json").read_text(encoding="utf-8"))
    assert meta["config_source"] == "profil.json"
    assert meta["config_sha256"] == _sha(src)


def test_journal_non_vide_apres_evenement(ctrl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctrl.start_recording()
    essai = ctrl.essai
    ctrl.log("évènement de test")
    ctrl.stop_recording()
    contenu = (essai.path / "journal.log").read_text(encoding="utf-8")
    assert "évènement de test" in contenu


def test_issue_arret_utilisateur(ctrl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctrl.start_recording()
    essai = ctrl.essai
    ctrl.stop_sequence()          # arrêt utilisateur explicite
    ctrl.stop_recording()
    meta = json.loads((essai.path / "essai.json").read_text(encoding="utf-8"))
    assert meta["issue"]["issue"] == ISSUE_ARRET_UTILISATEUR


def test_issue_declenchement_securite_via_trip(ctrl, tmp_path, monkeypatch):
    """Un déclenchement de sécurité pendant un essai inscrit l'issue en rouge
    (declenchement_securite) + la cause + un événement horodaté."""
    monkeypatch.chdir(tmp_path)
    ctrl.set_output("VLOAD", True)
    ctrl.start_recording()
    essai = ctrl.essai
    ctrl.emergency_stop("Surchauffe TS1 = 99°C")
    ctrl.stop_recording()

    meta = json.loads((essai.path / "essai.json").read_text(encoding="utf-8"))
    assert meta["issue"]["issue"] == ISSUE_DECLENCHEMENT
    assert "Surchauffe" in meta["issue"]["cause"]
    evts = meta["evenements_securite"]
    assert evts and evts[0]["type"] == "coupure_dure"
    assert evts[0]["horodatage"]


def test_issue_declenchement_non_declassee_par_fin_de_desalim(ctrl, tmp_path, monkeypatch):
    """La désalimentation de sécurité qui se « termine » ne doit pas ramener
    l'issue à 'termine' : le déclenchement reste inscrit."""
    monkeypatch.chdir(tmp_path)
    ctrl.start_recording()
    essai = ctrl.essai
    essai.set_issue(ISSUE_DECLENCHEMENT, cause="trip")
    essai.set_issue(ISSUE_TERMINE)   # tentative de déclassement
    assert essai.issue == ISSUE_DECLENCHEMENT
    ctrl.stop_recording()


def test_sequence_texte_archive(ctrl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctrl.start_recording()
    essai = ctrl.essai
    texte = "# séquence\nSET VLOAD V 5\nWAIT 1\n"
    ctrl.start_user_sequence([], text=texte)
    ctrl.runner.force_stop()
    ctrl.stop_recording()
    seq = essai.path / "sequence.seq"
    assert seq.exists()
    assert seq.read_text(encoding="utf-8") == texte


@pytest.mark.parametrize("nom, attendu_dans", [
    ('a/b c:*?"<>|d', "ab_cd"),
    ("  Essai  Final  ", "Essai_Final"),
    ('///:::', ""),
])
def test_noms_dossier_robustes(nom, attendu_dans):
    assert safe_folder_name(nom) == attendu_dans


def test_dossier_nom_interdit_cree_dossier_valide(ctrl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctrl.start_recording(nom='essai/x:y*?"<>|')
    essai = ctrl.essai
    ctrl.stop_recording()
    # Aucun caractère interdit dans le nom du dossier créé.
    assert essai.path.exists()
    assert not (set(essai.path.name) & set('/\\:*?"<>|'))
