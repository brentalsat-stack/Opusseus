"""Backtest testleri için tutarlı (hizalı) sentetik çok-zaman-dilimli mum üretici."""
import random

START = 1_700_000_000 - (1_700_000_000 % 86400)
TF_SECONDS = {"1d": 86400, "4h": 14400, "1h": 3600, "15m": 900, "5m": 300}


def make_5m(seed, days, start=100.0, wave_len=1200, drift=0.0):
    """Dalgalı rastgele yürüyüş; gerçekçi POI/BOS üretsin diye uzun dalgalar."""
    rng = random.Random(seed)
    price = start
    rows = []
    for i in range(days * 288):
        wave = 1.0 if (i // wave_len) % 2 == 0 else -1.0
        move = (wave * 0.012 + drift + rng.uniform(-0.09, 0.09)) * start / 100.0
        o = price
        c = max(o + move, 1.0)
        h = max(o, c) + rng.uniform(0.0, 0.05) * start / 100.0
        low = max(min(o, c) - rng.uniform(0.0, 0.05) * start / 100.0, 0.5)
        rows.append((START + i * 300, o, h, low, c, 10.0))
        price = c
    return rows


def aggregate(rows_5m, seconds):
    """5m mumlarını daha büyük zaman dilimine toplar (yalnızca tam dolu gruplar)."""
    per = seconds // 300
    out = []
    for i in range(0, len(rows_5m) - per + 1, per):
        group = rows_5m[i:i + per]
        if group[0][0] % seconds:
            continue
        out.append((group[0][0], group[0][1], max(r[2] for r in group), min(r[3] for r in group),
                    group[-1][4], sum(r[5] for r in group)))
    return out


def make_series(seed, days, **kwargs):
    five = make_5m(seed, days, **kwargs)
    return {"5m": five, "15m": aggregate(five, 900), "1h": aggregate(five, 3600),
            "4h": aggregate(five, 14400), "1d": aggregate(five, 86400)}
