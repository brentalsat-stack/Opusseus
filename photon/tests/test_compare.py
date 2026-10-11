"""Varyant karşılaştırma modu: override'lar, EXTREME_ALWAYS, V7 dağılımı, ay bazında huni, CLI (sırayla ve paralel)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.__main__ import main
from photon.backtest.compare import (CompareSpec, Variant, apply_overrides, format_compare, load_variants, run_compare,
                                     vshape_distribution)
from photon.backtest.report import monthly_funnel
from photon.config import load_config
from photon.data import CandleStore
from photon.risk.stops import StopParams
from photon.strategy.entry_model import EntryParams
from photon.tests.test_cli_structure import synth_m1

UTC = timezone.utc


def test_default_variants_file_matches_the_requested_set():
    spec = load_variants("variants.yaml")
    assert [v.name for v in spec.variants] == ["V0", "V1", "V2", "V3", "V4", "V5", "V6"]
    ov = {v.name: v.overrides for v in spec.variants}
    assert ov["V0"] == {} and ov["V1"] == {"entry_price_mode": "DISTAL"} and ov["V2"] == {"entry_price_mode": "EQ"}
    assert ov["V3"] == {"fixed_sl_pips": 3} and ov["V4"] == {"fixed_sl_pips": 5}
    assert ov["V5"] == {"entry_price_mode": "DISTAL", "entry_zone_choice": "EXTREME_ALWAYS"}
    assert ov["V6"] == {"range_extreme_filter.enabled": False} and spec.vshape_n == [5, 15, 20]


def test_overrides_apply_on_a_copy_and_default_config_is_untouched():
    cfg = load_config()
    v1 = apply_overrides(cfg, {"entry_price_mode": "DISTAL"})
    v3 = apply_overrides(cfg, {"fixed_sl_pips": 3, "range_extreme_filter.enabled": False})
    assert cfg.get("entry_price_mode") == "FIXED_SL" and cfg.get("fixed_sl_pips") == 2 and cfg.get("range_extreme_filter.enabled") is True
    assert StopParams.from_config(v1, "EURUSD").entry_price_mode == "DISTAL"
    assert StopParams.from_config(v3, "EURUSD").fixed_sl_pips == 3 and v3.get("range_extreme_filter.enabled") is False
    assert EntryParams.from_config(cfg, "EURUSD").entry_zone_choice == "FLIP_FIRST"
    assert EntryParams.from_config(apply_overrides(cfg, {"entry_zone_choice": "EXTREME_ALWAYS"}), "EURUSD").entry_zone_choice == "EXTREME_ALWAYS"
    with pytest.raises(KeyError):
        apply_overrides(cfg, {"entry_prize_mode": "EQ"})                  # yazım hatası → hata
    with pytest.raises(KeyError):
        apply_overrides(cfg, {"range_extreme_filter.nope": 1})


def test_extreme_always_ignores_an_available_flip_zone():
    from photon.tests.test_entry_model import build, run_path, make_choch, with_zones, zone, bos
    for choice, kind in (("FLIP_FIRST", "FLIP"), ("EXTREME_ALWAYS", "EXTREME")):
        em, ze15, ze1, m1s, states = build(zone_choice=choice)
        ch = make_choch()
        with_zones(ze1, ch)                                               # flip + extreme zon mevcut
        _, out, _ = run_path(em, ze1, m1s, states, zone(caused_events=[bos()]), ze15, choch=ch)
        sig = next(e for e in out if e.kind == "SIGNAL")
        assert sig.intent.entry_zone_kind == kind
        assert sig.intent.choch_gap is not None and sig.intent.choch_gap >= 0         # V7 için sinyal anında saklanır


def test_vshape_distribution_is_consistent_at_config_n_and_monotone_in_n():
    rows = []
    for gap, win in ((3, True), (8, False), (12, True), (18, False), (30, True)):
        earned = gap <= 10
        rows.append({"score": D(5) + (D(1) if earned else D(0)), "weight": D(1), "earned": earned, "win": win, "cls": "PRO",
                     "gap": gap})
    txt = vshape_distribution(rows, [5, 15, 20], 10)
    lines = {int(l.split()[0]): l for l in txt.splitlines()[1:]}
    assert lines[10].split()[1] == "2" and "(config)" in lines[10]
    assert [int(lines[n].split()[1]) for n in (5, 10, 15, 20)] == [1, 2, 3, 4]       # N büyüdükçe kazanan sayısı artar
    assert lines[10].split()[-2] == "0"                                               # config N'de puanı değişen yok


@pytest.fixture
def small_env(tmp_path):
    text = (open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite"))
            .replace("logs/photon.log", str(tmp_path / "p.log")).replace("M15: 30,", "M15: 5,").replace("D1: 365, H4: 365", "D1: 5, H4: 5")
            .replace("M1: 7}", "M1: 1}"))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(text, encoding="utf-8")
    store = CandleStore(tmp_path / "c.sqlite")
    store.put_candles("HISTDATA", synth_m1(datetime(2021, 8, 20, tzinfo=UTC), 14 * 1440))
    store.close()
    (tmp_path / "v.yaml").write_text("""
variants:
  - {name: A0, desc: base, overrides: {}}
  - {name: A1, desc: distal, overrides: {entry_price_mode: DISTAL}}
  - {name: A2, desc: sl3, overrides: {fixed_sl_pips: 3}}
vshape_report: {base: A0, n_values: [5, 20]}
""", encoding="utf-8")
    return tmp_path, cfgp


@pytest.mark.parametrize("jobs", [1, 2])
def test_backtest_compare_cli_runs_all_variants_same_data_in_one_table(small_env, capsys, jobs):
    tmp, cfgp = small_env
    rc = main(["backtest-compare", "--config", str(cfgp), "--start", "2021-09-01", "--end", "2021-09-03", "--variants", str(tmp / "v.yaml"),
               "--out", str(tmp / "o"), "--jobs", str(jobs)])
    out = capsys.readouterr().out
    assert rc == 0 and "VARYANT KARŞILAŞTIRMA" in out
    for name in ("A0", "A1", "A2"):
        assert name in out and (tmp / "o" / name / "EURUSD_report.txt").exists()
    for col in ("strike%", "ort R net", "top R net", "getiri%", "maxDD%", "maks kayıp serisi", "komisyon/risk%", "≤5dk stop"):
        assert col in out
    assert "Trend sınıfı kırılımı" in out and "V7" in out and (tmp / "o" / "compare.csv").exists()


def test_compare_is_deterministic_and_baseline_equals_plain_backtest(small_env, tmp_path):
    tmp, cfgp = small_env
    spec = load_variants(str(tmp / "v.yaml"))
    spec = CompareSpec(spec.variants[:1], [], None)
    start, end = datetime(2021, 9, 1, tzinfo=UTC), datetime(2021, 9, 4, tzinfo=UTC)
    a = run_compare(str(cfgp), spec, "HISTDATA", "EURUSD", start, end, D(10000), tmp / "o1", 1, progress=lambda *_: None)[0]
    b = run_compare(str(cfgp), spec, "HISTDATA", "EURUSD", start, end, D(10000), tmp / "o2", 1, progress=lambda *_: None)[0]
    assert a["metrics"] == b["metrics"] and a["funnel"] == b["funnel"]
    # tek başına backtest ile aynı sonuç
    from photon.backtest.engine import BacktestEngine
    from photon.data import tools
    cfg = load_config(cfgp)
    m1 = tools.load_m1(cfg, "HISTDATA", "EURUSD", start - timedelta(days=7), end)
    res = BacktestEngine(cfg, "EURUSD", start, end, D(10000)).run(m1)
    assert a["metrics"].n == len(res.trades) and a["metrics"].total_r == sum((t.r_gross for t in res.trades), D(0))


def test_monthly_funnel_lists_empty_months_with_reason(small_env):
    from photon.backtest.engine import BacktestEngine
    from photon.data import tools
    tmp, cfgp = small_env
    cfg = load_config(cfgp)
    start, end = datetime(2021, 9, 1, tzinfo=UTC), datetime(2021, 9, 4, tzinfo=UTC)
    res = BacktestEngine(cfg, "EURUSD", start, end, D(10000)).run(tools.load_m1(cfg, "HISTDATA", "EURUSD", start - timedelta(days=7), end))
    rows = monthly_funnel(res)
    assert [r["ay"] for r in rows] == ["2021-09"] and rows[0]["mitigasyon"] >= rows[0]["izin_ok"] >= 0
