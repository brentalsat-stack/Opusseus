import logging

from photon.logging_setup import setup_logging


def ours(log):
    return [h for h in log.handlers if getattr(h, "_photon_handler", False)]   # pytest kendi capture handler'larını ekleyebilir


def test_file_and_console(tmp_path, capsys):
    f = tmp_path / "sub" / "photon.log"
    log = setup_logging("INFO", f, console=True)
    logging.getLogger("photon.test").info("merhaba")
    for h in log.handlers:
        h.flush()
    assert "merhaba" in f.read_text(encoding="utf-8")
    assert "merhaba" in capsys.readouterr().err
    assert len(ours(log)) == 2
    setup_logging("INFO", f, console=True)  # idempotent
    assert len(ours(log)) == 2
    setup_logging("INFO", f, console=False)
    for h in ours(log):
        h.close()
