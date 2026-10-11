"""V8 — M15 icra modeli (T-M15BT): rol kayması, %25 kuralı, seans kapısı, haber penceresi, rollover dolum yasağı, küçük POI'yi rafine etmeme."""
import dataclasses
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.backtest.compare import apply_overrides, load_variants, missing_inputs
from photon.backtest.engine import BacktestEngine
from photon.config import load_config
from photon.data import Candle, Timeframe
from photon.risk.session import SessionClock
from photon.risk.stops import Rejected, Side, StopParams, ZoneBounds, plan_entry
from photon.signals.news_blackout import NewsBlackout, NewsEvent
from photon.strategy.entry_model import EntryParams
from photon.strategy.poi import POIParams
from photon.strategy.profile import PROFILES, profile_from_config
from photon.strategy.runner import StrategyRunner
from photon.strategy.state_machine import State
from photon.tests.test_management import intent_for_output
from photon.tests.test_runner import cfg_with_policies, synth

UTC = timezone.utc
PIP = D("0.0001")
V8 = {"execution_profile": "M15", "entry_price_mode": "FIB25_FROM_PROXIMAL", "session_gate": False, "min_refine_pips": 3}


def v8cfg(extra=None, base=None):
    return apply_overrides(base or load_config(), {**V8, **(extra or {})})


# ---------------- profil ----------------
def test_default_profile_is_m1_and_v8_shifts_roles_one_level_up():
    assert profile_from_config(load_config()) is PROFILES["M1"]
    p = profile_from_config(v8cfg())
    assert (p.exec_tf, p.hi, p.mid, p.poi_tfs) == (Timeframe.M15, Timeframe.D1, Timeframe.H4, (Timeframe.D1, Timeframe.H4))
    ep, pp = EntryParams.from_config(v8cfg(), "EURUSD"), POIParams.from_config(v8cfg())
    assert ep.refine_min_tf is Timeframe.D1 and ep.min_refine_pips == 3
    assert pp.poi_min_tf is Timeframe.H4 and pp.nested_child_tf is Timeframe.H4
    ep0, pp0 = EntryParams.from_config(load_config(), "EURUSD"), POIParams.from_config(load_config())
    assert ep0.refine_min_tf is Timeframe.H4 and ep0.min_refine_pips == 0 and pp0.poi_min_tf is Timeframe.M15
    with pytest.raises(ValueError):
        profile_from_config(apply_overrides(load_config(), {"execution_profile": "M5"}))


def test_variants_file_has_v8_a_b_c_and_default_config_is_unchanged():
    spec = load_variants("variants.yaml")
    names = [v.name for v in spec.variants]
    assert {"V8a", "V8b", "V8c"} <= set(names) and spec.detail is not None
    ov = {v.name: v.overrides for v in spec.variants}
    assert ov["V8a"]["execution_profile"] == "M15" and ov["V8a"]["session_gate"] is False and ov["V8a"]["min_refine_pips"] == 3
    assert ov["V8b"]["news_blackout"]["window_min"] == 30 and ov["V8c"]["entry_price_mode"] == "FIB25_FROM_DISTAL"
    cfg = load_config()
    assert cfg.get("execution_profile") is None and cfg.get("session_gate") is None and cfg.get("entry_price_mode") == "FIXED_SL"
    v8b = next(v for v in spec.variants if v.name == "V8b")
    assert "haber dosyası yok" in (missing_inputs(v8b) or "")                    # dosya yoksa atlanır, çökmez


# ---------------- %25 kuralı ----------------
SP = StopParams(PIP, "FIB25_FROM_PROXIMAL", D(2), D(0), D(2))
Z = ZoneBounds(D("1.1020"), D("1.1000"))          # 20 pip yükseklik


def test_fib25_from_proximal_long_and_short():
    p = plan_entry(Z, Side.LONG, SP)                # proximal = üst: giriş = 1.1020 − 0.25×0.0020; stop alt − 1 pipette
    assert (p.entry, p.stop) == (D("1.10150"), D("1.09999"))
    s = plan_entry(Z, Side.SHORT, SP)               # proximal = alt: giriş = 1.1000 + 0.25×0.0020; stop üst + 1 pipette
    assert (s.entry, s.stop) == (D("1.10050"), D("1.10201"))
    assert p.pip_risk == D("15.1")


def test_fib25_from_distal_alternative_interpretation():
    sp = dataclasses.replace(SP, entry_price_mode="FIB25_FROM_DISTAL")
    assert plan_entry(Z, Side.LONG, sp).entry == D("1.10050")                   # distal (alt) + %25
    assert plan_entry(Z, Side.SHORT, sp).entry == D("1.10150")


def test_fib25_small_zone_hits_min_sl_and_pct_is_configurable():
    tiny = ZoneBounds(D("1.1002"), D("1.1000"))                                  # 2 pip: risk = 1.5 + 0.1 < 2
    assert isinstance(plan_entry(tiny, Side.LONG, SP), Rejected)
    assert plan_entry(Z, Side.LONG, dataclasses.replace(SP, fib_pct=D(50))).entry == D("1.10100")
    assert StopParams.from_config(load_config(), "EURUSD").fib_pct == 25


# ---------------- seans / haber ----------------
def test_session_gate_off_allows_any_time_except_blackout_and_news():
    cfg = v8cfg()
    clk = SessionClock.from_config(cfg)
    assert clk.may_open(datetime(2021, 9, 1, 3, 0, tzinfo=UTC)).allowed                      # normalde seans dışı
    assert clk.may_open(datetime(2021, 9, 1, 21, 30, tzinfo=UTC)).reason == "BLACKOUT"
    assert not SessionClock.from_config(load_config()).may_open(datetime(2021, 9, 1, 3, 0, tzinfo=UTC)).allowed   # varsayılan değişmedi


def test_news_blackout_window_edges_csv_and_session_clock(tmp_path):
    f = tmp_path / "n.csv"
    f.write_text("# yorum\ndate,time_utc,event\n2021-09-03,12:30,NFP\n2021-09-03,18:00,FOMC\n", encoding="utf-8")
    nb = NewsBlackout.from_csv(f, 30)
    t = datetime(2021, 9, 3, 12, 30, tzinfo=UTC)
    assert nb.in_window(t - timedelta(minutes=30)) and nb.in_window(t + timedelta(minutes=29))
    assert not nb.in_window(t - timedelta(minutes=31)) and not nb.in_window(t + timedelta(minutes=30))     # [olay−w, olay+w)
    assert nb.event_in_window(datetime(2021, 9, 3, 18, 10, tzinfo=UTC)).name == "FOMC"
    assert not nb.in_window(datetime(2021, 9, 3, 15, 0, tzinfo=UTC))
    cfg = v8cfg({"news_blackout": {"file": str(f), "window_min": 30}})
    d = SessionClock.from_config(cfg).may_open(t)
    assert (d.allowed, d.reason) == (False, "NEWS_WINDOW")
    (tmp_path / "bad.csv").write_text("date,time_utc,event\nxx,yy,E\n", encoding="utf-8")
    with pytest.raises(ValueError):
        NewsBlackout.from_csv(tmp_path / "bad.csv")


# ---------------- küçük POI rafine edilmez ----------------
def test_poi_smaller_than_min_refine_pips_is_not_refined():
    from photon.tests.test_entry_model import build, zone, bos, MarketView
    em, ze15, ze1, m1s, states = build()
    poi = zone(caused_events=[bos()])                                              # 4 pip yüksekliğinde (10..14)
    em.p = dataclasses.replace(em.p, refine_min_tf=Timeframe.M15)                  # bu POI "üst TF" sayılsın
    view = MarketView(datetime(2021, 9, 1, tzinfo=UTC), [], 0, [], m1s, ze1, states, [], {Timeframe.M15: []}, D(10000))
    s = em.watch(poi, ze15, {})
    assert em._targets(s, view) == []                                              # rafine zon yok → hedef boş
    em.p = dataclasses.replace(em.p, min_refine_pips=D(5))
    assert em._targets(s, view) == [poi]                                           # 4 < 5 pip → POI'nin kendisi
    em.p = dataclasses.replace(em.p, min_refine_pips=D(4))
    assert em._targets(s, view) == []                                              # 4 ≥ 4: rafine edilir


# ---------------- uçtan uca: runner + engine ----------------
@pytest.fixture(scope="module")
def v8_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v8")
    cfg = apply_overrides(cfg_with_policies(tmp), V8)
    m1 = synth(datetime(2021, 8, 2, tzinfo=UTC), 40 * 1440, seed=7, amp=18)
    e = BacktestEngine(cfg, "EURUSD", datetime(2021, 8, 30, tzinfo=UTC), datetime(2021, 9, 10, tzinfo=UTC), D(10000))
    res = e.run(m1)
    return e, res, m1, cfg


def test_v8_runner_steps_on_m15_closes_only_and_uses_d1_h4_engines(v8_run):
    e, res, m1, cfg = v8_run
    r = e.runner
    assert set(r.struct) == {Timeframe.D1, Timeframe.H4} and r.profile.name == "M15"
    assert r.exec_c and all(c.tf is Timeframe.M15 for c in r.exec_c)
    assert len(r.exec_c) < len(m1) / 10 and r.model.p.refine_min_tf is Timeframe.D1
    assert all(s.poi.tf in (Timeframe.D1, Timeframe.H4) for s in r.model.setups + r.model.archive)       # POI'ler H4/D1 (M15 değil)
    assert res.setups and any(rec[1] == "MITIGATED" for s in res.setups for rec in s.trace)


def test_v8_is_deterministic_and_signals_are_not_in_session_gated(v8_run):
    e, res, m1, cfg = v8_run
    e2 = BacktestEngine(cfg, "EURUSD", res.start, res.end, D(10000)).run(m1)
    key = lambda r: [(ev.kind, ev.time, ev.setup.id) for ev in r.events]
    assert key(res) == key(e2)
    for ev in res.events:
        if ev.kind == "SIGNAL":
            assert not e.clock.in_blackout(ev.time)                                      # rollover'da yeni emir yok
    for t in res.trades:
        assert t.fill_time >= t.intent.time


def _engine_with_pending(tmp_path, extra=None):
    cfg = apply_overrides(cfg_with_policies(tmp_path), {**V8, **(extra or {})})
    eng = BacktestEngine(cfg, "EURUSD", datetime(2021, 9, 1, tzinfo=UTC), datetime(2021, 9, 2, tzinfo=UTC), D(10000))
    ev = intent_for_output()
    eng.pending[ev.setup.id] = ev.setup
    return eng, ev.setup, ev.intent


def _c(t, o, h, l, c):
    f = lambda x: D(str(x))
    return Candle("EURUSD", Timeframe.M1, t, f(o), f(h), f(l), f(c), True)


def touch_candle(eng, it, t):
    if it.side is Side.LONG:
        return _c(t, it.entry, it.entry, it.entry - eng.spread, it.entry)
    return _c(t, it.entry, it.entry, it.entry, it.entry)


def test_v8_no_fill_during_rollover_blackout_but_default_profile_fills(tmp_path):
    eng, s, it = _engine_with_pending(tmp_path)
    eng._pre_step(touch_candle(eng, it, datetime(2021, 9, 1, 21, 30, tzinfo=UTC)))
    assert s.id in eng.pending and not eng.positions and eng.extra_stats["blackout_fill_blocked"] == 1
    eng._pre_step(touch_candle(eng, it, datetime(2021, 9, 1, 23, 0, tzinfo=UTC)))        # blackout bitti (bitiş dışlanır)
    assert eng.positions and s.id not in eng.pending
    base = BacktestEngine(cfg_with_policies(tmp_path), "EURUSD", datetime(2021, 9, 1, tzinfo=UTC), datetime(2021, 9, 2, tzinfo=UTC), D(10000))
    ev = intent_for_output()
    base.pending[ev.setup.id] = ev.setup
    base._pre_step(touch_candle(base, ev.intent, datetime(2021, 9, 1, 21, 30, tzinfo=UTC)))
    assert base.positions                                                              # varsayılan profil: davranış değişmedi


def test_v8_m1_level_cancel_when_first_target_reached_before_fill(tmp_path):
    eng, s, it = _engine_with_pending(tmp_path)
    t = datetime(2021, 9, 1, 9, 0, tzinfo=UTC)
    far = it.cancel_if_reaches
    hi, lo = (far + PIP, it.entry + 5 * PIP) if it.side is Side.LONG else (it.entry - 5 * PIP, far - PIP)
    eng._pre_step(_c(t, it.entry + 6 * PIP if it.side is Side.LONG else it.entry - 6 * PIP, max(hi, lo), min(hi, lo),
                     it.entry + 6 * PIP if it.side is Side.LONG else it.entry - 6 * PIP))
    assert s.state is State.WATCHING and s.id not in eng.pending
    assert eng.events[-1].kind == "CANCELLED" and eng.events[-1].reason == "FIRST_TARGET_REACHED_BEFORE_FILL"


def test_v8b_news_window_cancels_pending_blocks_fill_and_flattens_open_position(tmp_path):
    t_news = datetime(2021, 9, 1, 12, 30, tzinfo=UTC)
    f = tmp_path / "n.csv"
    f.write_text(f"date,time_utc,event\n{t_news:%Y-%m-%d},{t_news:%H:%M},NFP\n", encoding="utf-8")
    ov = {"news_blackout": {"file": str(f), "window_min": 30}}
    # 1) bekleyen emir pencere başında iptal
    eng, s, it = _engine_with_pending(tmp_path, ov)
    eng._pre_step(_c(t_news - timedelta(minutes=30), it.entry + 20 * PIP, it.entry + 20 * PIP, it.entry + 19 * PIP, it.entry + 20 * PIP))
    assert s.state is State.WATCHING and not eng.pending and eng.extra_stats["news_orders_cancelled"] == 1
    assert eng.events[-1].reason == "NEWS_WINDOW"
    # 2) açık pozisyon pencere başında piyasadan kapanır (long bid / short ask açılışı)
    eng, s, it = _engine_with_pending(tmp_path, ov)
    eng._pre_step(touch_candle(eng, it, t_news - timedelta(minutes=40)))
    assert eng.positions
    t0 = t_news - timedelta(minutes=30)
    o = it.entry + D("0.00003") if it.side is Side.LONG else it.entry - D("0.00003")
    eng._pre_step(_c(t0, o, o, o, o))
    assert not eng.positions and len(eng.closed) == 1
    tr = eng.closed[0]
    f_ = tr.position.fills[-1]
    assert f_.leg == "NEWS_EXIT" and f_.time == t0 and eng.extra_stats["news_exits"] == 1
    assert f_.price == (o if it.side is Side.LONG else o + eng.spread) and tr.commission >= 4
    # 3) pencerede dolum yok
    eng, s, it = _engine_with_pending(tmp_path, ov)
    eng._pre_step(touch_candle(eng, it, t_news))
    assert not eng.positions


def test_compare_cli_detail_csv_only_and_skip_missing_news(tmp_path, capsys):
    from photon.__main__ import main
    from photon.data import CandleStore
    from photon.tests.test_cli_structure import synth_m1
    text = (open("config.yaml", encoding="utf-8").read().replace("data_cache/photon.sqlite", str(tmp_path / "c.sqlite"))
            .replace("logs/photon.log", str(tmp_path / "p.log")).replace("M15: 30,", "M15: 5,").replace("D1: 365, H4: 365", "D1: 20, H4: 20")
            .replace("M1: 7}", "M1: 1}"))
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(text, encoding="utf-8")
    store = CandleStore(tmp_path / "c.sqlite")
    store.put_candles("HISTDATA", synth_m1(datetime(2021, 8, 1, tzinfo=UTC), 40 * 1440))
    store.close()
    rc = main(["backtest-compare", "--config", str(cfgp), "--start", "2021-09-01", "--end", "2021-09-12", "--variants", "variants.yaml",
               "--only", "V0,V8a,V8b", "--out", str(tmp_path / "o"), "--jobs", "1"])
    cap = capsys.readouterr()
    assert rc == 0 and "V8b" in cap.err and "ATLANDI" in cap.out
    for n in ("V0", "V8a"):
        assert (tmp_path / "o" / n / "EURUSD_trades_detail.csv").exists()
    assert not (tmp_path / "o" / "V8b").exists()
    assert main(["backtest-compare", "--config", str(cfgp), "--start", "2021-09-01", "--end", "2021-09-02", "--variants", "variants.yaml",
                 "--only", "NOPE", "--out", str(tmp_path / "o2")]) == 2
