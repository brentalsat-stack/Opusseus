"""Uzun koşu regresyonu (Q-S11): iç yapı motoru referansı kaybedip aylarca CHoCH üretmemezlik etmemeli."""
import dataclasses
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.__main__ import main
from photon.data import CandleStore, Candle, Timeframe
from photon.data.models import PriceSide
from photon.structure import StructureEngine, StructureParams
from photon.structure.models import EventType
from photon.tests.test_runner import synth

UTC = timezone.utc
PIP = D("0.0001")


def run_internal(minutes_days, seed, amp, reacquire):
    m1 = synth(datetime(2016, 1, 4, tzinfo=UTC), minutes_days * 1440, seed=seed, amp=amp)
    p = dataclasses.replace(StructureParams.internal_only_params(PIP), reacquire_ref=reacquire)
    st = StructureEngine(Timeframe.M1, p, None, datetime(2016, 1, 4, tzinfo=UTC))
    cnt = Counter()
    for q in m1:
        for e in st.update(q.to_candle(PriceSide.BID)):
            if e.type is EventType.CHOCH:
                cnt[f"{e.time:%Y-%m}"] += 1
    months = sorted({f"{q.open_time:%Y-%m}" for q in m1})[:-1]          # son (kısmi) ay hariç
    return st, [cnt.get(m, 0) for m in months]


def test_legacy_engine_froze_for_months_and_fixed_engine_does_not():
    """Hata yeniden üretimi: eski davranışta (reacquire_ref=False) bazı aylar HİÇ CHoCH yok ve referanssız süre on binlerce mum; düzeltmede her ay CHoCH var."""
    old, old_months = run_internal(330, seed=1, amp=6, reacquire=False)
    assert min(old_months) == 0 and old.iref_none_max_run > 20000            # kilitlenme gerçekten üretiliyor (test gücü)
    new, months = run_internal(330, seed=1, amp=6, reacquire=True)
    assert min(months) > 500 and new.iref_none_max_run < 100 and new.ref_reacquired > 0


@pytest.mark.parametrize("seed,amp", [(2, 25), (5, 14)])
def test_internal_structure_produces_choch_every_month_over_a_long_run(seed, amp):
    st, months = run_internal(330, seed, amp, True)
    assert len(months) >= 10 and all(n > 100 for n in months), months
    assert st.iref_none_max_run < 100


def test_reacquire_ref_unit_stale_pending_no_longer_blocks_reference():
    m1 = synth(datetime(2016, 1, 4, tzinfo=UTC), 400, seed=4, amp=10)
    p = StructureParams.internal_only_params(PIP)
    st = StructureEngine(Timeframe.M1, p, None, datetime(2016, 1, 4, tzinfo=UTC))
    legacy = StructureEngine(Timeframe.M1, dataclasses.replace(p, reacquire_ref=False), None, datetime(2016, 1, 4, tzinfo=UTC))
    cs = [q.to_candle(PriceSide.BID) for q in m1]
    for c in cs[:200]:
        st.update(c)
        legacy.update(c)
    for eng in (st, legacy):                               # kilitlenme durumu: referans yok + fiyattan çok uzakta eski bekleyen aday
        eng.iref = None
        eng._defer = None
        eng.ipend = (D("0.0001") if eng.e < 0 else D(100), 0)        # bekleyen aday fiyattan çok uzakta: asla kırılmaz
    for c in cs[200:215]:
        st.update(c)
        legacy.update(c)
    assert st.iref is not None and st.ref_reacquired >= 1 and st.iref_none_max_run < 15
    assert legacy.iref is None                              # eski davranış: kilitli kalır


# ---------------- uçtan uca (V8 profili hızlıdır): her ay icra motoru CHoCH üretmeli ----------------
def test_backtest_exec_engine_emits_choch_every_month_and_monthly_funnel_shows_it(tmp_path):
    from photon.backtest.compare import apply_overrides
    from photon.backtest.engine import BacktestEngine
    from photon.backtest.report import monthly_funnel
    from photon.tests.test_runner import cfg_with_policies
    from photon.tests.test_v8 import V8
    cfg = apply_overrides(cfg_with_policies(tmp_path), V8)
    m1 = synth(datetime(2016, 1, 4, tzinfo=UTC), 420 * 1440, seed=1, amp=6)
    res = BacktestEngine(cfg, "EURUSD", datetime(2016, 1, 4, tzinfo=UTC), datetime(2017, 2, 20, tzinfo=UTC), D(10000)).run(m1)
    rows = monthly_funnel(res)[1:-1]
    assert len(rows) >= 10 and all(r["icra_choch_olay"] > 0 for r in rows), [(r["ay"], r["icra_choch_olay"]) for r in rows]
    assert res.limit_report["struct_exec_iref_none_max_run"] < 100 and res.limit_report["struct_exec_ref_reacquired"] > 0
    assert all(res.limit_report[f"struct_{tf}_iref_none_max_run"] < 1000 for tf in ("D1", "H4"))


# ---------------- --periods: veri start'tan SONRA başlıyorsa warm-up kontrolü çökmemeli ----------------
def test_compare_periods_when_data_starts_after_start_runs_with_warning(tmp_path, capsys):
    from photon.tests.test_cli_structure import synth_m1
    text = (open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite"))
            .replace("logs/photon.log", str(tmp_path / "p.log")))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(text, encoding="utf-8")
    st = CandleStore(tmp_path / "c.sqlite")
    st.put_candles("HISTDATA", synth_m1(datetime(2021, 1, 3, 22, tzinfo=UTC), 20 * 1440))
    st.close()
    (tmp_path / "v.yaml").write_text("variants:\n  - {name: A0, desc: base, overrides: {}}\n", encoding="utf-8")
    rc = main(["backtest-compare", "--config", str(cfgp), "--periods", "2021..2021", "--variants", str(tmp_path / "v.yaml"), "--jobs", "1",
               "--out", str(tmp_path / "o")])
    cap = capsys.readouterr()
    assert rc == 0 and "UYARI: veri 2021-01-03" in cap.err and "Yıllık kırılım" in cap.out
    assert main(["backtest-compare", "--config", str(cfgp), "--start", "2019-01-01", "--end", "2019-12-31", "--variants", str(tmp_path / "v.yaml"),
                 "--out", str(tmp_path / "o2")]) == 2                                   # veri aralıkla kesişmiyor
