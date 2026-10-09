import logging

from photon.logging_setup import setup_logging


def test_file_and_console(tmp_path, capsys):
    f = tmp_path / "sub" / "photon.log"
    log = setup_logging("INFO", f, console=True)
    logging.getLogger("photon.test").info("merhaba")
    for h in log.handlers:
        h.flush()
    assert "merhaba" in f.read_text(encoding="utf-8")
    assert "merhaba" in capsys.readouterr().err
    assert len(log.handlers) == 2
    setup_logging("INFO", f, console=True)  # idempotent
    assert len(log.handlers) == 2
    setup_logging("INFO", f, console=False)
    for h in list(log.handlers):
        h.close()
