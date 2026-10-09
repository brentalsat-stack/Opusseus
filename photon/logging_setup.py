"""Logging: ekran + dosya (DECISIONS §1: bildirim = ekran + log dosyası). Zaman damgası UTC."""
from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT = "%(asctime)sZ %(levelname)-7s %(name)s: %(message)s"
_TAG = "_photon_handler"


def setup_logging(level: str, file: str | Path, console: bool = True) -> logging.Logger:
    """Kök 'photon' logger'ını kurar (idempotent). Dosya dizini yoksa oluşturulur."""
    logger = logging.getLogger("photon")
    logger.setLevel(level.upper())
    logger.propagate = False
    for h in [h for h in logger.handlers if getattr(h, _TAG, False)]:
        logger.removeHandler(h)
        h.close()

    fmt = logging.Formatter(_FMT, datefmt="%Y-%m-%dT%H:%M:%S")
    fmt.converter = time.gmtime
    path = Path(file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")]
    if console:
        handlers.append(logging.StreamHandler())
    for h in handlers:
        h.setFormatter(fmt)
        setattr(h, _TAG, True)
        logger.addHandler(h)
    return logger


def setup_from_config(cfg) -> logging.Logger:
    return setup_logging(cfg.get("logging.level", "INFO"), cfg.get("logging.file", "logs/photon.log"))
