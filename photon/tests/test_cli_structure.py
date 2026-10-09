"""CLI uçtan uca: sentetik M1 önbelleği → resample → yapı (warm-up) → CSV + PNG."""
import csv
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from photon.__main__ import main
from photon.data import OHLC, CandleStore, QuoteCandle, Timeframe

UTC = timezone.utc


def synth_m1(start, minutes, seed=3):
    rnd, p, out = random.Random(seed), D("1.1800"), []
    for i in range(minutes):
        t = start + timedelta(minutes=i)
        o = p
        c = o + D(rnd.randint(-15, 15)) / D(10000)
        h, l = max(o, c) + D(rnd.randint(0, 5)) / D(10000), min(o, c) - D(rnd.randint(0, 5)) / D(10000)
        out.append(QuoteCandle("EURUSD", Timeframe.M1, t, OHLC(o, h, l, c), OHLC(o + D("0.0001"), h + D("0.0001"), l + D("0.0001"), c + D("0.0001")), True, 3))
        p = c
    return out


def test_structure_cli_auto_warmup(tmp_path, capsys):
    cfg_text = open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite")) \
        .replace("logs/photon.log", str(tmp_path / "p.log")).replace("M15: 30,", "M15: 5,")
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(cfg_text, encoding="utf-8")
    store = CandleStore(tmp_path / "c.sqlite")
    store.put_candles("DUKASCOPY", synth_m1(datetime(2021, 8, 25, tzinfo=UTC), 12 * 1440))
    store.close()
    out = tmp_path / "out"
    rc = main(["structure", "--config", str(cfgp), "--source", "DUKASCOPY", "--tf", "M15",
               "--start", "2021-08-31", "--end", "2021-09-05", "--out", str(out)])
    assert rc == 0
    rows = list(csv.DictReader((out / "EURUSD_M15_structure.csv").open()))
    assert rows and {"warmup", "type", "dir", "level"} <= set(rows[0])
    assert any(r["type"] == "BOS" for r in rows)
    live = [r for r in rows if r["warmup"] == "False"]
    warm = [r for r in rows if r["warmup"] == "True"]
    assert warm and live                      # warm-up olayları işaretli, canlı dönem de var
    assert all(r["time_utc"] < "2021-08-31T00:00:00Z" for r in warm)
    assert (out / "EURUSD_M15_structure.png").stat().st_size > 1000
    assert "canlı" in capsys.readouterr().out


def test_structure_cli_without_data(tmp_path, capsys):
    cfg_text = open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "e.sqlite")) \
        .replace("logs/photon.log", str(tmp_path / "p.log"))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(cfg_text, encoding="utf-8")
    assert main(["structure", "--config", str(cfgp), "--source", "DUKASCOPY", "--tf", "M15",
                 "--start", "2021-09-01", "--end", "2021-09-02", "--out", str(tmp_path / "o")]) == 2


def test_zones_cli_end_to_end(tmp_path, capsys):
    cfg_text = open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite")) \
        .replace("logs/photon.log", str(tmp_path / "p.log")).replace("M15: 30,", "M15: 5,")
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(cfg_text, encoding="utf-8")
    store = CandleStore(tmp_path / "c.sqlite")
    store.put_candles("HISTDATA", synth_m1(datetime(2021, 8, 25, tzinfo=UTC), 12 * 1440))
    store.close()
    out = tmp_path / "z"
    rc = main(["zones", "--config", str(cfgp), "--source", "HISTDATA", "--tf", "M15",
               "--start", "2021-08-31", "--end", "2021-09-05", "--out", str(out)])
    assert rc == 0
    rows = list(csv.DictReader((out / "EURUSD_M15_zones.csv").open()))
    assert rows and {"kind", "origin", "valid", "caused_by", "is_flip", "sweep_zone"} <= set(rows[0])
    assert {r["origin"] for r in rows} >= {"PIVOT"} and any(r["valid"] == "True" for r in rows)
    assert (out / "EURUSD_M15_zones.png").stat().st_size > 1000
    o = capsys.readouterr().out
    assert "Zon özeti" in o and "geçerli (SD-R005)" in o


def test_zones_cli_d1_needs_draw_mode_decision(tmp_path):
    import pytest
    cfg_text = open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite")) \
        .replace("logs/photon.log", str(tmp_path / "p.log"))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(cfg_text, encoding="utf-8")
    store = CandleStore(tmp_path / "c.sqlite")
    store.put_candles("HISTDATA", synth_m1(datetime(2021, 8, 1, tzinfo=UTC), 30 * 1440))
    store.close()
    with pytest.raises(ValueError, match="Q-Z3"):
        main(["zones", "--config", str(cfgp), "--source", "HISTDATA", "--tf", "D1", "--start", "2021-08-20",
              "--end", "2021-08-30", "--out", str(tmp_path / "o")])
