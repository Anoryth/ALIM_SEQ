"""Rapport d'essai — couche données + HTML (pur Python).

Les tests de génération PDF (ReportLab) et de graphiques (matplotlib) sont ignorés
si ces bibliothèques sont absentes (``importorskip``).
"""

import json
import re

import pytest

from alim_seq.rapport import (construire_html, stats_capteurs, stats_voies,
                              _fr, evenements, trip_info)


# --- CSV synthétique connu (pour vérifier les statistiques exactement) --------
HEADER = ["horodatage", "t_s", "TS1_C", "TS1_V",
          "VLOAD_Vset", "VLOAD_Iset", "VLOAD_Vmeas", "VLOAD_Imeas", "VLOAD_out",
          "securite"]
ROWS = [
    ["t0", "0.0", "50.0", "1.0", "6.0", "1.0", "5.0", "1.0", "1", "OK"],
    ["t1", "1.0", "70.0", "1.0", "6.0", "1.0", "6.0", "2.0", "1", "OK"],
    ["t2", "2.0", "90.0", "1.0", "6.0", "1.0", "4.0", "0.0", "1", "CRITICAL"],
]


def test_stats_voies_exactes():
    sv = stats_voies(HEADER, ROWS)
    assert sv["VLOAD"]["v"] == pytest.approx((4.0, 6.0, 5.0))
    assert sv["VLOAD"]["i"] == pytest.approx((0.0, 2.0, 1.0))


def test_stats_capteurs_exactes():
    sc = stats_capteurs(HEADER, ROWS, warnings={"TS1": 80.0})
    assert sc["TS1"]["c"] == pytest.approx((50.0, 90.0, 70.0))
    # Un seul intervalle (t1->t2, dt=1s) est au-dessus de 80 °C.
    assert sc["TS1"]["alerte_s"] == pytest.approx(1.0)


# --- Dossier de fixture écrit à la main ---------------------------------------
def _make_dossier(tmp_path, nom="Essai démo", issue="declenchement_securite",
                  cause="Surchauffe TS1"):
    d = tmp_path / "essai1"
    d.mkdir()
    meta = {
        "version": "1.0.0", "mode": "simulation", "nom": nom, "operateur": "Alice",
        "debut": "2026-07-04T10:00:00", "fin": "2026-07-04T10:05:00",
        "config_source": None, "config_sha256": "abcdef0123456789" * 4,
        "sequence_sha256": None, "conclusion": "",
        "issue": {"issue": issue, "cause": cause},
        "evenements_securite": [{"horodatage": "2026-07-04T10:03:00",
                                 "type": "trip", "message": cause}],
    }
    (d / "essai.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "config.json").write_text(json.dumps(
        {"temperatures": {"TS1": {"warning": 80, "critical": 100}},
         "channels": {"VLOAD": {"supply": "PSU2", "channel": 2}}}), encoding="utf-8")
    with (d / "mesures.csv").open("w", encoding="utf-8", newline="") as f:
        import csv
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(ROWS)
    (d / "journal.log").write_text(
        "[10:00:01] Enregistrement démarré\n"
        "[10:03:00] !!! Surchauffe TS1 = 90°C\n", encoding="utf-8")
    return d


def test_sections_presentes(tmp_path):
    html = construire_html(_make_dossier(tmp_path))
    for attendu in ("Test report — ALIM_SEQ", "Summary",
                    "Operator conclusion", "Per-channel statistics",
                    "Timeline", "Appendix A", "Appendix B"):
        assert attendu in html
    assert "Measurement points" in html
    assert "3 points" in html                  # 3 points de mesure + synthèse


def test_bandeau_simulation(tmp_path):
    html = construire_html(_make_dossier(tmp_path))
    assert "SIMULATION TEST" in html


def test_issue_declenchement_en_rouge(tmp_path):
    html = construire_html(_make_dossier(tmp_path))
    assert "SAFETY TRIP" in html
    assert "Surchauffe TS1" in html
    assert "#C62828" in html   # rouge réservé à la sécurité


def test_conclusion_vide(tmp_path):
    html = construire_html(_make_dossier(tmp_path), conclusion="")
    assert "(not provided)" in html


def test_conclusion_renseignee_et_echappee(tmp_path):
    html = construire_html(_make_dossier(tmp_path),
                           conclusion="Résultat <b>bon</b> & validé")
    assert "Résultat &lt;b&gt;bon&lt;/b&gt; &amp; validé" in html


def test_echappement_html_nom_essai(tmp_path):
    """Un nom d'essai malicieux ne doit pas injecter de balise."""
    html = construire_html(_make_dossier(tmp_path, nom="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_images_referencees(tmp_path):
    d = _make_dossier(tmp_path)
    html = construire_html(d, images={"courbes_vi": "courbes_vi.png",
                                      "courbes_temp": "courbes_temp.png"})
    assert "src='courbes_vi.png'" in html
    assert "src='courbes_temp.png'" in html


def test_pas_de_verdict_de_conformite(tmp_path):
    """Le rapport ne prononce jamais 'conforme'/'non conforme' de lui-même."""
    html = construire_html(_make_dossier(tmp_path)).lower()
    assert "conforme" not in html


def test_smoke_pdf_offscreen(tmp_path):
    """Couche PDF (ReportLab) : génère un PDF non vide (> 10 ko) + les PNG."""
    pytest.importorskip("reportlab")
    pytest.importorskip("matplotlib")
    from alim_seq.rapport import generer_rapport

    d = _make_dossier(tmp_path)
    pdf = generer_rapport(d, conclusion="Essai de démonstration.")
    assert pdf.exists() and pdf.stat().st_size > 10_000
    assert (d / "rapport.html").exists()
    assert (d / "courbes.png").exists()
    # La conclusion saisie est persistée dans essai.json pour les régénérations.
    meta = json.loads((d / "essai.json").read_text(encoding="utf-8"))
    assert meta["conclusion"] == "Essai de démonstration."


def test_rapport_depuis_essai_reel(ctrl, tmp_path, monkeypatch):
    """Bout en bout : un essai réellement enregistré (avec trip) régénère un
    rapport PDF depuis son seul dossier, cause en rouge (critères 1 et 2)."""
    pytest.importorskip("reportlab")
    pytest.importorskip("matplotlib")
    from alim_seq.rapport import generer_rapport

    monkeypatch.chdir(tmp_path)
    ctrl.set_output("VLOAD", True)
    ctrl.start_recording(nom="Essai réel")
    dossier = ctrl.essai.path
    ctrl._temp_cycle()
    for _ in range(4):
        ctrl._meas_cycle()
    ctrl.emergency_stop("Surchauffe simulée")
    ctrl.stop_recording()

    pdf = generer_rapport(dossier)
    assert pdf.exists() and pdf.stat().st_size > 10_000
    html = (dossier / "rapport.html").read_text(encoding="utf-8")
    assert "SAFETY TRIP" in html
    assert "Surchauffe simulée" in html


# ============================ Mission 6 — Tâche 3 ============================

def test_fr():
    from alim_seq import i18n
    # English base: decimal point.
    i18n.set_language("en")
    assert _fr(1234.5, 1) == "1234.5"
    assert _fr(3.14159, 2) == "3.14"
    # French: decimal comma.
    i18n.set_language("fr")
    try:
        assert _fr(1234.5, 1) == "1234,5"
        assert _fr(3.14159, 2) == "3,14"
    finally:
        i18n.set_language("en")
    assert _fr(80, 0) == "80"
    assert _fr(None) == "—"
    assert _fr(float("nan")) == "—"
    assert _fr(float("inf")) == "—"


def test_evenements_recales_sur_le_csv(tmp_path):
    """Recalage des événements du journal sur l'axe des temps du CSV, via
    l'horodatage absolu de la 1re ligne (fixture à horodatages connus)."""
    d = tmp_path / "e"
    d.mkdir()
    header = ["horodatage", "t_s", "TS1_C"]
    rows = [["2026-07-04T10:00:00", "0.0", "20"],
            ["2026-07-04T10:00:20", "20.0", "20"]]
    with (d / "mesures.csv").open("w", encoding="utf-8", newline="") as f:
        import csv
        csv.writer(f).writerows([header] + rows)
    (d / "journal.log").write_text(
        "[10:00:05] Palier atteint\n"
        "[10:00:12] !!! Surchauffe TS1\n", encoding="utf-8")
    evs = evenements(d, header, rows)
    assert len(evs) == 2
    assert evs[0]["t_s"] == pytest.approx(5.0)
    assert evs[0]["danger"] is False
    assert evs[1]["t_s"] == pytest.approx(12.0)
    assert evs[1]["danger"] is True


def test_temps_en_cc_exact():
    sv = stats_voies(HEADER, ROWS)
    # t1 (dt=1s) : Imeas 2.0 >= 0.98*Iset(1.0) et sortie active -> 1 s en CC ;
    # t2 : Imeas 0.0 -> hors CC. Temps actif = 2 s -> 50 %.
    assert sv["VLOAD"]["cc_s"] == pytest.approx(1.0)
    assert sv["VLOAD"]["cc_pct"] == pytest.approx(50.0)
    assert sv["VLOAD"]["consigne_debut"] == pytest.approx((6.0, 1.0))
    assert sv["VLOAD"]["consigne_fin"] == pytest.approx((6.0, 1.0))


def test_excursions_temperature_exactes():
    sc = stats_capteurs(HEADER, ROWS, warnings={"TS1": 80.0}, criticals={"TS1": 85.0})
    assert sc["TS1"]["excursions"] == 1        # une montée au-dessus de 80 °C
    assert sc["TS1"]["alerte_s"] == pytest.approx(1.0)
    assert sc["TS1"]["critique_s"] == pytest.approx(1.0)   # t2=90 >= 85, dt=1s


def test_trip_info_uniquement_si_declenchement():
    meta_dec = {"issue": {"issue": "declenchement_securite", "cause": "Surchauffe TS1"},
                "evenements_securite": []}
    ti = trip_info(meta_dec, HEADER, ROWS)
    assert ti is not None and ti["capteur"] == "TS1"
    assert trip_info({"issue": {"issue": "termine"}}, HEADER, ROWS) is None


def test_dossier_autonome(tmp_path):
    """Le HTML ne référence QUE des fichiers présents dans le dossier (logo copié,
    courbes générées) — régénérable et transportable."""
    pytest.importorskip("reportlab")
    pytest.importorskip("matplotlib")
    import re
    from alim_seq.rapport import generer_rapport
    d = _make_dossier(tmp_path)
    generer_rapport(d, conclusion="ok")
    html = (d / "rapport.html").read_text(encoding="utf-8")
    srcs = re.findall(r"<img[^>]*\ssrc=['\"]([^'\"]+)['\"]", html)
    assert srcs, "aucune image dans le rapport"
    for src in srcs:
        assert not src.startswith(("http", "/", "..")), f"référence externe : {src}"
        assert (d / src).exists(), f"fichier manquant dans le dossier : {src}"


def test_pagination_plus_de_3_pages(tmp_path):
    """Pied de page paginé : un rapport long (> 3 pages) se génère non vide."""
    pytest.importorskip("reportlab")
    pytest.importorskip("matplotlib")
    from alim_seq.rapport import generer_rapport
    d = _make_dossier(tmp_path)
    # Une séquence très longue étale l'annexe A sur plusieurs pages.
    (d / "sequence.seq").write_text(
        "\n".join(f"LOG ligne de sequence numero {i}" for i in range(400)),
        encoding="utf-8")
    pdf = generer_rapport(d)
    assert pdf.exists() and pdf.stat().st_size > 10_000
    data = pdf.read_bytes()
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", data)]
    assert counts and max(counts) > 3, f"pages={counts} (attendu > 3)"


def test_pdf_embarque_les_courbes(tmp_path):
    """Les PNG des courbes doivent réellement être embarqués dans le PDF : un
    rapport AVEC images pèse nettement plus qu'un rapport identique SANS."""
    pytest.importorskip("reportlab")
    pytest.importorskip("matplotlib")
    from alim_seq.rapport import exporter_pdf, rendre_graphiques

    d = _make_dossier(tmp_path)
    images = rendre_graphiques(d, d)
    assert images and all((d / name).exists() for name in images.values())
    exporter_pdf(d, d / "avec.pdf", images=images)
    exporter_pdf(d, d / "sans.pdf", images={})
    avec = (d / "avec.pdf").stat().st_size
    sans = (d / "sans.pdf").stat().st_size
    assert avec > sans + 5000, f"images non embarquées (avec={avec}, sans={sans})"
