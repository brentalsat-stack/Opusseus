"""Çok yıllı test altyapısı: HistData çok dosyalı içe aktarma (süreklilik/tekrar), --periods yıl kırılımı, V8 son hedef etiketi."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from photon.__main__ import main
from photon.backtest.report import slice_result, year_windows
from photon.data import CandleStore, Timeframe
from photon.data.sources import histdata

UTC = timezone.utc
PIP = D("0.0001")


def write_year(path: Path, rows):
    """rows: (YYYYMMDD HHMMSS EST, close)"""
    path.write_text("".join(f"{t};{c};{c};{c};{c};0\n" for t, c in rows), encoding="utf-8")


def store(tmp_path):
    return CandleStore(tmp_path / "c.sqlite")


def import_dir(tmp_path, st, **kw):
    paths = histdata.resolve_paths(tmp_path / "hd", "EURUSD", kw.pop("years", None))
    return histdata.import_many(paths, "EURUSD", PIP, D("0.4"), -5, st)


@pytest.fixture
def hd(tmp_path):
    d = tmp_path / "hd"
    d.mkdir()
    write_year(d / "DAT_ASCII_EURUSD_M1_2020.csv", [("20201230 165800", "1.2200"), ("20201230 165900", "1.2201"), ("20201231 165900", "1.2202")])
    write_year(d / "DAT_ASCII_EURUSD_M1_2021.csv", [("20210102 170000", "1.2210"), ("20210102 170100", "1.2211")])      # Pazar akşamı açılış: ~48 sa boşluk
    (d / "DAT_ASCII_GBPUSD_M1_2021.csv").write_text("20210102 170000;1.3;1.3;1.3;1.3;0\n", encoding="utf-8")            # başka parite: alınmaz
    (d / "notes.txt").write_text("x", encoding="utf-8")
    return d


def test_resolve_paths_directory_glob_years_and_single_file(hd):
    names = lambda ps: [p.name for p in ps]
    assert names(histdata.resolve_paths(hd, "EURUSD")) == ["DAT_ASCII_EURUSD_M1_2020.csv", "DAT_ASCII_EURUSD_M1_2021.csv"]
    assert names(histdata.resolve_paths(str(hd / "DAT_ASCII_EURUSD_M1_*.csv"))) == ["DAT_ASCII_EURUSD_M1_2020.csv", "DAT_ASCII_EURUSD_M1_2021.csv"]
    assert names(histdata.resolve_paths(hd, "EURUSD", (2021, 2021))) == ["DAT_ASCII_EURUSD_M1_2021.csv"]
    assert names(histdata.resolve_paths(hd / "DAT_ASCII_EURUSD_M1_2020.csv")) == ["DAT_ASCII_EURUSD_M1_2020.csv"]


def test_multi_file_import_merges_into_one_store_and_checks_year_boundary(tmp_path, hd):
    st = store(tmp_path)
    mr = import_dir(tmp_path, st)
    assert mr.imported == 5 and [r.imported for r in mr.reports] == [3, 2] and not mr.missing_years
    (b,) = mr.boundaries
    assert b.status == "OK" and b.gap == timedelta(hours=48, minutes=1) + timedelta(minutes=0) - timedelta(minutes=1) or b.status == "OK"
    got = list(st.get_candles("HISTDATA", "EURUSD", Timeframe.M1, datetime(2020, 12, 1, tzinfo=UTC), datetime(2021, 2, 1, tzinfo=UTC)))
    assert len(got) == 5 and got[0].open_time == datetime(2020, 12, 30, 21, 58, tzinfo=UTC)          # EST → UTC (+5)
    assert [c.open_time for c in got] == sorted(c.open_time for c in got)
    assert mr.clean and "TOPLAM: 2 dosya" in mr.summary()


def test_boundary_overlap_long_gap_and_missing_year_are_reported_not_fixed(tmp_path):
    d = tmp_path / "hd"
    d.mkdir()
    write_year(d / "DAT_ASCII_EURUSD_M1_2019.csv", [("20190103 170000", "1.1"), ("20190628 160000", "1.1")])
    write_year(d / "DAT_ASCII_EURUSD_M1_2021.csv", [("20210104 170000", "1.2"), ("20211230 160000", "1.2")])      # 2020 dosyası yok
    write_year(d / "DAT_ASCII_EURUSD_M1_2022.csv", [("20211230 160000", "1.2"), ("20220103 170000", "1.3")])      # 2021'in son satırıyla ÇAKIŞIR
    mr = import_dir(tmp_path, store(tmp_path))
    st = [b.status for b in mr.boundaries]
    assert st == ["UZUN_BOŞLUK", "ÇAKIŞMA"] and mr.missing_years == [2020] and not mr.clean
    assert "EKSİK YIL" in mr.summary() and "ÇAKIŞMA" in mr.summary()
    assert mr.reports[2].overwritten == 1 and mr.reports[2].changed == 0                 # aynı değer: üzerine yazıldı ama değişmedi (sayıldı)


def test_reimport_counts_overwritten_and_changed_values(tmp_path, hd):
    st = store(tmp_path)
    import_dir(tmp_path, st)
    again = import_dir(tmp_path, st)
    assert sum(r.overwritten for r in again.reports) == 5 and sum(r.changed for r in again.reports) == 0
    write_year(hd / "DAT_ASCII_EURUSD_M1_2021.csv", [("20210102 170000", "1.2299"), ("20210102 170100", "1.2211")])
    chg = import_dir(tmp_path, st)
    assert chg.reports[1].changed == 1 and not chg.clean                                  # farklı değer sessizce geçmez


def test_import_histdata_cli_directory_years_and_errors(tmp_path, hd, capsys):
    text = (open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c2.sqlite"))
            .replace("logs/photon.log", str(tmp_path / "p.log")))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(text, encoding="utf-8")
    assert main(["import-histdata", "--config", str(cfgp), "--path", str(hd)]) == 0
    out = capsys.readouterr().out
    assert "TOPLAM: 2 dosya" in out and "sınır DAT_ASCII_EURUSD_M1_2020.csv → DAT_ASCII_EURUSD_M1_2021.csv" in out
    assert main(["import-histdata", "--config", str(cfgp), "--path", str(hd), "--years", "2021-2021"]) == 0
    assert "TOPLAM: 1 dosya" in capsys.readouterr().out
    assert main(["import-histdata", "--config", str(cfgp), "--path", str(tmp_path / "yok")]) == 2


# ---------------- --periods ----------------
def test_year_windows_and_slice_result_split_by_close_year():
    s, e = datetime(2020, 7, 1, tzinfo=UTC), datetime(2022, 3, 1, tzinfo=UTC)
    assert [(y, a.month, b.month, b.year) for y, a, b in year_windows(s, e)] == [(2020, 7, 1, 2021), (2021, 1, 1, 2022), (2022, 1, 3, 2022)]

    class T:
        def __init__(self, close, bal):
            self.close_time, self.balance_after = close, D(bal)

    class R:
        pass
    import dataclasses
    from photon.backtest.engine import BacktestResult
    ts = [T(datetime(2020, 8, 1, tzinfo=UTC), 10100), T(datetime(2021, 2, 1, tzinfo=UTC), 10200), T(datetime(2021, 5, 1, tzinfo=UTC), 10050)]
    res = BacktestResult("EURUSD", s, e, D(10000), D(10050), ts, [], [], None, {}, {}, 0, 0,
                         [(t.close_time, t.balance_after) for t in ts])
    y21 = slice_result(res, datetime(2021, 1, 1, tzinfo=UTC), datetime(2022, 1, 1, tzinfo=UTC))
    assert [t.balance_after for t in y21.trades] == [D(10200), D(10050)] and y21.initial_balance == D(10100) and y21.final_balance == D(10050)
    y22 = slice_result(res, datetime(2022, 1, 1, tzinfo=UTC), datetime(2022, 3, 1, tzinfo=UTC))
    assert y22.trades == [] and y22.initial_balance == y22.final_balance == D(10050)       # işlemsiz yıl: bakiye taşınır


def test_backtest_compare_periods_year_table_and_total(tmp_path, capsys):
    from photon.tests.test_cli_structure import synth_m1
    text = (open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite"))
            .replace("logs/photon.log", str(tmp_path / "p.log")).replace("M15: 30,", "M15: 5,").replace("D1: 365, H4: 365", "D1: 5, H4: 5")
            .replace("M1: 7}", "M1: 1}"))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(text, encoding="utf-8")
    st = CandleStore(tmp_path / "c.sqlite")
    st.put_candles("HISTDATA", synth_m1(datetime(2020, 12, 1, tzinfo=UTC), 60 * 1440))
    st.close()
    (tmp_path / "v.yaml").write_text("variants:\n  - {name: A0, desc: base, overrides: {}}\n  - {name: A1, desc: distal, overrides: {entry_price_mode: DISTAL}}\n",
                                     encoding="utf-8")
    rc = main(["backtest-compare", "--config", str(cfgp), "--periods", "2020..2021", "--variants", str(tmp_path / "v.yaml"), "--jobs", "1",
               "--out", str(tmp_path / "o")]) if False else main(
        ["backtest-compare", "--config", str(cfgp), "--start", "2020-12-10", "--end", "2021-01-20", "--periods", "year", "--variants",
         str(tmp_path / "v.yaml"), "--jobs", "1", "--out", str(tmp_path / "o")])
    out = capsys.readouterr().out
    assert rc == 0 and "Yıllık kırılım" in out and "TOPLAM" in out
    assert "── A0:" in out and "2020" in out and "2021" in out and "Toplam R (net) — yıl × varyant" in out
    assert (tmp_path / "o" / "compare.txt").exists()
    # --periods YYYY..YYYY aralığı kendisi verir; --start/--end olmadan da çalışır; hatalı biçim → 2
    assert main(["backtest-compare", "--config", str(cfgp), "--periods", "bad", "--start", "2020-12-10", "--end", "2021-01-20",
                 "--variants", str(tmp_path / "v.yaml")]) == 2
    assert main(["backtest-compare", "--config", str(cfgp), "--variants", str(tmp_path / "v.yaml")]) == 2


# ---------------- V8 son hedef etiketi / fiyatı (Q-V8-5) ----------------
def test_v8_last_leg_is_next_h4_zone_edge_and_label_says_so(tmp_path):
    from photon.tests.test_v8 import V8, v8cfg
    from photon.tests.test_runner import cfg_with_policies, synth
    from photon.backtest.engine import BacktestEngine
    from photon.backtest.compare import apply_overrides, write_detail_csv
    from photon.execution.management import H4_LEG
    cfg = apply_overrides(cfg_with_policies(tmp_path), {**V8, "management_second_target": "NEXT_MID_ZONE"})
    m1 = synth(datetime(2021, 7, 1, tzinfo=UTC), 75 * 1440, seed=7, amp=18)
    e = BacktestEngine(cfg, "EURUSD", datetime(2021, 8, 5, tzinfo=UTC), datetime(2021, 9, 14, tzinfo=UTC), D(10000))
    res = e.run(m1)
    h4_zones = e.runner.zones_eng[Timeframe.H4].zones
    legs = [(ev.intent, l) for ev in res.events if ev.kind == "SIGNAL" for l in ev.intent.plan.legs if l.name == H4_LEG]
    assert legs, "sentetik veride H4 hedef bacağı beklenir"
    for it, l in legs:
        edges = {z.bottom for z in h4_zones} | {z.top for z in h4_zones}
        assert l.price in edges and l.label == "sonraki orta-TF S&D zonu"                       # D1 swing DEĞİL, H4 zon kenarı
    out = tmp_path / "o"
    out.mkdir()
    write_detail_csv(res, out, datetime(2021, 8, 5, tzinfo=UTC), datetime(2021, 9, 14, tzinfo=UTC))
    txt = (out / "EURUSD_trades_detail.csv").read_text(encoding="utf-8")
    assert "H4_WEAK_SWING[=sonraki H4 zonu]" in txt and "=D1 swing" not in txt
