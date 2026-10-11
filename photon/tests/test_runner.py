"""MTF toplayıcı (resample ile tutarlılık) ve StrategyRunner uçtan uca duman/determinizm testleri."""
import random
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.config import load_config
from photon.data import BoundarySpec, OHLC, QuoteCandle, Timeframe, resample
from photon.strategy.runner import MtfAggregator, StrategyRunner

UTC = timezone.utc


def synth(start, minutes, seed=7, amp=14, weekends=True):
    rnd, p, out = random.Random(seed), D("1.1800"), []
    for i in range(minutes):
        t = start + timedelta(minutes=i)
        if weekends and (t.weekday() == 5 or (t.weekday() == 4 and t.hour >= 21) or (t.weekday() == 6 and t.hour < 21)):
            continue
        o = p
        c = o + D(rnd.randint(-amp, amp)) / D(10000)
        h, l = max(o, c) + D(rnd.randint(0, 4)) / D(10000), min(o, c) - D(rnd.randint(0, 4)) / D(10000)
        out.append(QuoteCandle("EURUSD", Timeframe.M1, t, OHLC(o, h, l, c), OHLC(o + D("0.00004"), h + D("0.00004"), l + D("0.00004"), c + D("0.00004")), True, 3))
        p = c
    return out


def cfg_with_policies(tmp_path):
    text = (open("config.yaml", encoding="utf-8").read()
            .replace("duplicate_signal_policy: REQUIRED", "duplicate_signal_policy: REJECT")
            .replace("opposite_signal_policy: REQUIRED", "opposite_signal_policy: REJECT")
            .replace("logs/photon.log", str(tmp_path / "p.log")))
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return load_config(p)


def test_aggregator_matches_resample_for_all_htf_including_weekend_gaps():
    cfg = load_config()
    spec = BoundarySpec.from_config(cfg)
    m1 = synth(datetime(2021, 8, 30, tzinfo=UTC), 12 * 1440)
    agg = MtfAggregator(spec)
    got = {tf: [] for tf in (Timeframe.D1, Timeframe.H4, Timeframe.M15)}
    for c in m1:
        for q in agg.feed(c):
            got[q.tf].append(q)
    for tf in got:
        ref = [q for q in resample(m1, tf, spec) if q.complete]
        assert [(q.open_time, q.bid, q.ask) for q in got[tf]] == [(q.open_time, q.bid, q.ask) for q in ref], tf.value
        assert len(ref) > 5


def test_aggregator_emits_htf_before_ltf_order_and_closes_on_last_minute():
    spec = BoundarySpec.from_config(load_config())
    agg = MtfAggregator(spec)
    t0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
    emitted = []
    for i in range(15):
        emitted += agg.feed(synth(t0, 15, weekends=False)[i])
    assert [q.tf for q in emitted] == [Timeframe.M15] and emitted[0].open_time == t0     # 08:14 M1'i M15'i kapatır


@pytest.fixture(scope="module")
def run_result(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("run")
    cfg = cfg_with_policies(tmp)
    m1 = synth(datetime(2021, 8, 2, tzinfo=UTC), 35 * 1440, seed=11, amp=18)
    live_from = datetime(2021, 8, 30, tzinfo=UTC)

    def go():
        r = StrategyRunner(cfg, "EURUSD", live_from, D(10000))
        evs = []
        for q in m1:
            evs += r.on_m1(q)
        return r, evs
    t = time.time()
    r1, e1 = go()
    dt = time.time() - t
    r2, e2 = go()
    return r1, e1, r2, e2, dt, len(m1)


def test_runner_smoke_structures_zones_and_pois_are_built(run_result):
    r, evs, _, _, dt, n = run_result
    assert all(r.struct[tf].state().swing_trend.value != "UNDEFINED" for tf in r.struct)       # warm-up yapıyı kurdu
    assert r.m1_struct.state().internal_trend.value != "UNDEFINED"
    assert len(r.zones_eng[Timeframe.M15].zones) > 10 and r._watched
    assert dt < 120, f"{n} M1 mumu {dt:.0f} sn sürdü"                                          # performans tabanı


def test_runner_is_deterministic(run_result):
    _, e1, _, e2, _, _ = run_result
    key = lambda evs: [(e.kind, e.time, e.reason, e.setup.id, getattr(e.intent, "entry", None)) for e in evs]
    assert key(e1) == key(e2)


def test_warmup_period_never_progresses_setups_or_emits(run_result):
    r, evs, _, _, _, _ = run_result
    assert all(e.time >= r.live_from for e in evs)
    for s in r.model.setups:
        assert all(h[0] >= r.live_from for h in s.history)


def test_runner_requires_policy_decisions_failfast():
    from photon.config import ConfigError
    text = open("config.yaml", encoding="utf-8").read().replace("duplicate_signal_policy: REJECT", "duplicate_signal_policy: REQUIRED")
    import pathlib, tempfile
    p = pathlib.Path(tempfile.mkdtemp()) / "c.yaml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate_signal_policy"):
        StrategyRunner(load_config(p), "EURUSD", datetime(2021, 9, 1, tzinfo=UTC), D(10000))


def test_limit_report_has_all_q_l3_counters(run_result):
    rep = run_result[0].limit_report()
    assert {"liquidation_window_capped", "liquidation_window_capped_no_sweep", "zones_m1_retired", "zones_m1_retired_valid",
            "zones_M15_range_lookback_exhausted"} <= set(rep) and all(v >= 0 for v in rep.values())
    assert rep["zones_m1_retired"] > 0                      # 1 günden eski M1 zonları gerçekten emekli oluyor
