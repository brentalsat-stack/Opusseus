"""Adım 1 için internetsiz temel yardımcı doğrulaması."""
from datetime import datetime, timezone
import os
import tempfile

import config
import utils


def main():
    # Test çıktılarını geçici alana yazar; gerçek botun Documents yoluna dokunmaz.
    with tempfile.TemporaryDirectory(prefix="phantom_step1_") as test_root:
        config.BASE_DIR = test_root
        config.CACHE_DIR = os.path.join(test_root, "cache")
        config.SCANS_DIR = os.path.join(test_root, "scans")
        config.LOGS_DIR = os.path.join(test_root, "logs")
        utils.ensure_directories()
        utils.log("Adım 1 test log satırı")
        assert all(os.path.isdir(path) for path in (config.CACHE_DIR, config.SCANS_DIR, config.LOGS_DIR))

    now = datetime.now(timezone.utc)
    print("Şu an UTC:", now.isoformat())
    print("Şu an New York:", utils.utc_to_new_york(now).isoformat())

    examples = [
        ("Ocak", datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)),
        ("Temmuz", datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)),
        ("Kasım geçiş günü", datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)),
    ]
    for label, value in examples:
        print("{} UTC {} -> NY {}".format(label, value.isoformat(), utils.utc_to_new_york(value).isoformat()))

    assert utils.validate_candle({"t": 1, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10})
    assert utils.utc_to_new_york(datetime(2026, 1, 15, 12, tzinfo=timezone.utc)).utcoffset().total_seconds() == -18000
    assert utils.utc_to_new_york(datetime(2026, 7, 15, 12, tzinfo=timezone.utc)).utcoffset().total_seconds() == -14400
    print("test_step1: OK")


if __name__ == "__main__":
    main()
