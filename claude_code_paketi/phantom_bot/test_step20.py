"""Adım 20: Twelve Data önbelleği, kaydedildiğinde açık olan mumu kapanmış gibi sunmaz."""
import os
import tempfile
import time

import config
import data_twelvedata
from test_step15 import candle


def main():
    root = tempfile.mkdtemp(prefix="phantom_step20_")
    config.CACHE_DIR = os.path.join(root, "cache")
    config.SCANS_DIR = os.path.join(root, "scans")
    config.LOGS_DIR = os.path.join(root, "logs")
    path = data_twelvedata._cache_path("EUR/USD", "4h", 500)
    real_time = time.time
    try:
        # 4h mumu 08:00'da başlar; 11:30'da kaydedilen önbellekte 08:00 mumu henüz eksiktir.
        base = 1790000000 - (1790000000 % 14400)
        saved_at = base + 3.5 * 3600
        candles = [candle(1, 1.1, 0.9, 1.0, base - 14400), candle(1, 1.05, 0.99, 1.02, base)]
        time.time = lambda: saved_at
        data_twelvedata._write_cache(path, candles)
        # Aynı mum hâlâ açıkken (11:45) önbellek kullanılabilir.
        time.time = lambda: base + 3.75 * 3600
        assert data_twelvedata._read_cache(path, 3600, "4h") == candles
        # Mum kapandıktan sonra (12:10) TTL dolmasa da önbellek reddedilir.
        time.time = lambda: base + 4 * 3600 + 600
        assert data_twelvedata._read_cache(path, 3600, "4h") is None
        # Günlük önbellek de gün sınırında reddedilir.
        daily = data_twelvedata._cache_path("EUR/USD", "1day", 500)
        day_start = 1790000000 - (1790000000 % 86400)
        time.time = lambda: day_start + 20 * 3600
        data_twelvedata._write_cache(daily, candles)
        time.time = lambda: day_start + 86400 + 1800
        assert data_twelvedata._read_cache(daily, 21600, "1day") is None
        print("Önbellek yarım mumu sınırdan sonra kullanmıyor: GEÇTİ")
    finally:
        time.time = real_time
    print("test_step20: OK")


if __name__ == "__main__":
    main()
