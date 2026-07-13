"""Test du journal applicatif (fichier)."""


def test_file_logging_writes(tmp_path, cfg):
    from alim_seq.controller import Controller
    c = Controller(cfg)
    log_path = c.enable_file_logging(str(tmp_path / "app.log"))
    c.log("message de test 123")
    text = log_path.read_text(encoding="utf-8")
    assert "message de test 123" in text
    # Pas de doublon de handler si on réactive.
    again = c.enable_file_logging(str(tmp_path / "app.log"))
    assert again == log_path
    c.close()
