"""HistData içe aktarıcı: format, sabit EST→UTC, ask=bid+spread, hata sayımı, CLI uçtan uca."""
import csv
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.__main__ import main
from photon.config import ConfigError, load_config
from photon.data import CandleStore, Timeframe, bin_bounds, BoundarySpec
from photon.data.sources import histdata

UTC = timezone.utc
PIP = D("0.0001")


def write(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def read_all(path, **kw):
    rep = histdata.ImportReport()
    out = list(histdata.iter_m1(path, "EURUSD", PIP, D("0.4"), -5, rep))
    return out, rep


def test_parse_format_est_to_utc_and_ask(tmp_path):
    f = write(tmp_path / "d.csv", ["20210104 170000;1.224610;1.224780;1.224610;1.224780;0",
                                   "20210104 170100;1.224780;1.224880;1.224620;1.224700;0"])
    out, rep = read_all(f)
    c = out[0]
    assert c.open_time == datetime(2021, 1, 4, 22, 0, tzinfo=UTC)               # EST 17:00 = 22:00 UTC
    assert (c.bid.open, c.bid.high, c.bid.low, c.bid.close) == (D("1.224610"), D("1.224780"), D("1.224610"), D("1.224780"))
    assert c.ask.open == D("1.224610") + D("0.00004") and c.ask.high == D("1.224780") + D("0.00004")   # 0.4 pip
    assert c.tf is Timeframe.M1 and c.complete and rep.clean and rep.imported == 2


def test_fixed_est_has_no_dst_so_summer_rows_shift_by_5h(tmp_path):
    f = write(tmp_path / "d.csv", ["20210901 160000;1.18;1.18;1.18;1.18;0", "20210901 235900;1.18;1.18;1.18;1.18;0"])
    out, _ = read_all(f)
    assert out[0].open_time == datetime(2021, 9, 1, 21, 0, tzinfo=UTC)          # sabit UTC-5
    assert out[1].open_time == datetime(2021, 9, 2, 4, 59, tzinfo=UTC)
    # Yaz: gerçek NY 17:00 (EDT) = 21:00 UTC → D1 mumunun açılışı; HistData'da bu satır 16:00 "EST" etiketlidir
    spec = BoundarySpec.from_config(load_config())
    assert bin_bounds(out[0].open_time, Timeframe.D1, spec)[0] == out[0].open_time
    # Kış: "17:00 EST" = 22:00 UTC = NY 17:00 EST → gün açılışı
    w = datetime(2021, 1, 4, 22, 0, tzinfo=UTC)
    assert bin_bounds(w, Timeframe.D1, spec)[0] == w


def test_volume_ignored_blank_lines_ok(tmp_path):
    f = write(tmp_path / "d.csv", ["20210104 170000;1.1;1.2;1.0;1.1;9999", "", "20210104 170100;1.1;1.1;1.1;1.1;0"])
    out, rep = read_all(f)
    assert len(out) == 2 and rep.rows == 2 and out[0].n_ticks is None


def test_duplicates_out_of_order_invalid_are_counted_not_hidden(tmp_path):
    f = write(tmp_path / "d.csv", [
        "20210104 170100;1.1;1.2;1.0;1.1;0",
        "20210104 170000;1.1;1.2;1.0;1.1;0",       # sırasız (yine de alınır)
        "20210104 170100;1.3;1.4;1.2;1.3;0",       # tekrar (ilk satır tutulur)
        "20210104 170200;abc;1.2;1.0;1.1;0",       # sayı hatası
        "20210104 170300;1.1;1.0;1.2;1.1;0",       # high < low
        "20210104 170400;1.1;1.2;1.0",             # eksik alan
        "badtime;1.1;1.2;1.0;1.1;0",
        "20210104 170500;1.1;1.2;1.0;1.1;0"])
    out, rep = read_all(f)
    assert rep.imported == 3 and rep.duplicates == 1 and rep.out_of_order == 1 and len(rep.invalid) == 4
    assert [n for n, _ in rep.invalid] == [4, 5, 6, 7] and not rep.clean
    assert next(c for c in out if c.open_time.minute == 1).bid.open == D("1.1")     # ilk satır kazanır (UTC 22:01)


def test_import_file_into_store_roundtrip(tmp_path):
    f = write(tmp_path / "d.csv", [f"20210104 17{m:02d}00;1.2000{m};1.2010{m};1.1990{m};1.2005{m};0" for m in range(5)])
    store = CandleStore(":memory:")
    rep = histdata.import_file(f, "EURUSD", PIP, D("0.4"), -5, store)
    got = list(store.get_candles("HISTDATA", "EURUSD", Timeframe.M1, datetime(2021, 1, 4, tzinfo=UTC), datetime(2021, 1, 5, tzinfo=UTC)))
    assert rep.imported == 5 == len(got) and got[0].bid.open == D("1.20000") and got[0].ask.close == D("1.20050") + D("0.00004")


def test_config_values_and_gate():
    cfg = load_config()
    assert cfg.get("data.backtest.primary") == "HISTDATA" and cfg.get("costs.spread_pips") == D("0.4")
    assert cfg.get("costs.spread") == "FIXED" and cfg.get("data.backtest.histdata.utc_offset_hours") == -5
    cfg.require("hist_histdata")
    assert cfg.get("data.backtest.dukascopy.base_url")         # Dukascopy kodda/config'te durur ama varsayılan değil


# ---------------- CLI uçtan uca (sentetik HistData dosyası) ----------------
def synth_file(path, start_est, days=30, seed=5):
    """Hafta içi sürekli, hafta sonu (Cum 17:00 EST → Paz 17:00 EST) boşluklu, bazı rastgele eksik dakikalar."""
    rnd, p = random.Random(seed), D("1.1800")
    rows, t = [], start_est
    end = start_est + timedelta(days=days)
    while t < end:
        wd, hm = t.weekday(), t.hour * 60 + t.minute
        closed = (wd == 4 and hm >= 17 * 60) or wd == 5 or (wd == 6 and hm < 17 * 60)
        if not closed and rnd.random() > 0.002:          # ~%0.2 eksik dakika (tick yok)
            o = p
            c = o + D(rnd.randint(-12, 12)) / D(10000)
            h = max(o, c) + D(rnd.randint(0, 4)) / D(10000)
            l = min(o, c) - D(rnd.randint(0, 4)) / D(10000)
            rows.append(f"{t:%Y%m%d %H%M%S};{o:.5f};{h:.5f};{l:.5f};{c:.5f};0")
            p = c
        t += timedelta(minutes=1)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows)


def test_cli_import_check_and_structure(tmp_path, capsys):
    data = tmp_path / "hist.csv"
    n = synth_file(data, datetime(2021, 8, 1, 17, 0))                 # Pazar 17:00 EST'den 30 gün
    cfg_text = (open("config.yaml", encoding="utf-8").read()
                .replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite"))
                .replace("logs/photon.log", str(tmp_path / "p.log"))
                .replace("data_samples/histdata/DAT_ASCII_EURUSD_M1_2021.csv", str(data))
                .replace("M15: 30,", "M15: 10,"))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(cfg_text, encoding="utf-8")
    assert main(["import-histdata", "--config", str(cfgp)]) == 0
    assert f"{n} içe aktarıldı" in capsys.readouterr().out

    rc = main(["data-check", "--config", str(cfgp), "--start", "2021-08-02", "--end", "2021-08-30"])
    out = capsys.readouterr().out
    assert rc == 3                                                     # eksik dakikalar engelleyici olarak raporlanır
    assert "WEEKEND_GAP: 4" in out and "MISSING boşluk:" in out and "toplam eksik mum:" in out

    out_dir = tmp_path / "out"
    assert main(["structure", "--config", str(cfgp), "--tf", "M15", "--start", "2021-08-16", "--end", "2021-08-30",
                 "--out", str(out_dir)]) == 0
    rows = list(csv.DictReader((out_dir / "EURUSD_M15_structure.csv").open()))
    assert rows and any(r["warmup"] == "True" for r in rows) and any(r["warmup"] == "False" for r in rows)
    # veri 2021-08-01'de başlıyor; H4/D1 için 365 gün yok → uyarı
    assert main(["structure", "--config", str(cfgp), "--tf", "H4", "--start", "2021-08-16", "--end", "2021-08-30",
                 "--out", str(out_dir)]) == 0
    err = capsys.readouterr().err
    assert "UYARI warm-up" in err and "mevcut verinin tamamı warm-up" in err


def test_fetch_histdata_points_to_import(tmp_path):
    with pytest.raises(ValueError, match="import-histdata"):
        from photon.data import tools
        tools.fetch(load_config(), "HISTDATA", "EURUSD", datetime(2021, 1, 1, tzinfo=UTC), datetime(2021, 1, 2, tzinfo=UTC))
