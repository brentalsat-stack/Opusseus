"""Test yardımcısı: deterministik sentetik mum serileriyle _scan_symbol çalıştırır."""
import random
import tempfile

import config
import phantom_scan

TF_SECONDS = {"1day": 86400, "4h": 14400, "1h": 3600, "15m": 900, "5m": 300}
END_T = 1790000000 - (1790000000 % 86400)  # sabit, gün başına hizalı


def make_series(seed, tf, count=500, start=100.0, drift=0.0):
    rng = random.Random("{}-{}".format(seed, tf))
    step = TF_SECONDS[tf]
    price = start
    candles = []
    t0 = END_T - count * step
    for i in range(count):
        wave = 1.0 if (i // 40) % 2 == 0 else -1.0
        move = (wave * 0.35 + drift + rng.uniform(-0.8, 0.8)) * start / 100.0
        o = price
        c = max(o + move, 1.0)
        h = max(o, c) + rng.uniform(0.05, 0.5) * start / 100.0
        low = min(o, c) - rng.uniform(0.05, 0.5) * start / 100.0
        candles.append({"t": t0 + i * step, "o": o, "h": h, "l": max(low, 0.5), "c": c, "v": 1.0})
        price = c
    return candles


def make_data(seed):
    series = {tf: make_series(seed, tf) for tf in TF_SECONDS}
    for tf in list(series):
        series[tf + "_last"] = series[tf][-1]
    return series


def isolate_dirs():
    root = tempfile.mkdtemp(prefix="phantom_synth_")
    config.BASE_DIR = root
    config.CACHE_DIR = root + "/cache"
    config.SCANS_DIR = root + "/scans"
    config.LOGS_DIR = root + "/logs"
    return root


def scan(seed, symbol="TESTUSDT", market="crypto"):
    """Verilen tohumla sentetik veriyi _scan_symbol'den geçirip (adaylar, özet) döndürür."""
    data = make_data(seed)
    original = phantom_scan._load_symbol_data
    phantom_scan._load_symbol_data = lambda *args, **kwargs: data
    try:
        return phantom_scan._scan_symbol(symbol, market, False, lambda *a: None)
    finally:
        phantom_scan._load_symbol_data = original
