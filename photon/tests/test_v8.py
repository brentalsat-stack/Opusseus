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
from photon.strategy.state_machine import Setup, State
from photon.structure.models import Trend
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


# ---------------- Q-E5: bir POI = en fazla bir sinyal (ömür boyu); mükerrer işlem kök nedeni ----------------
def _scenario(policy):
    from collections import Counter
    m1 = synth(datetime(2021, 7, 1, tzinfo=UTC), 75 * 1440, seed=7, amp=18)
    import tempfile, pathlib
    cfg = apply_overrides(cfg_with_policies(pathlib.Path(tempfile.mkdtemp())), {**V8, "duplicate_signal_policy": policy})
    res = BacktestEngine(cfg, "EURUSD", datetime(2021, 8, 5, tzinfo=UTC), datetime(2021, 9, 14, tzinfo=UTC), D(10000)).run(m1)
    return res, Counter(t.id for t in res.trades), Counter(e.setup.id for e in res.events if e.kind == "SIGNAL")


def test_reject_policy_gives_at_most_one_signal_and_one_trade_per_poi():
    old, old_ids, old_sig = _scenario("REJECT_WHILE_ACTIVE")          # eski davranış: yalnız eşzamanlı aktif sinyal engellenirdi
    assert max(old_ids.values()) >= 2                                  # kök neden: aynı kurulum kapanış/iptal sonrası yeniden sinyal verir (mükerrer id)
    new, ids, sig = _scenario("REJECT")
    assert ids and max(ids.values()) == 1 and max(sig.values()) == 1
    assert len({(t.id, t.fill_time) for t in new.trades}) == len(new.trades) and len({t.no for t in new.trades}) == len(new.trades)
    assert all(s.n_signals <= 1 for s in new.setups)


def test_v0_profile_also_has_unique_trade_ids_under_reject(synth_result_v0):
    res = synth_result_v0
    ids = [t.id for t in res.trades]
    assert res.trades and len(ids) == len(set(ids))
    sig = [e.setup.id for e in res.events if e.kind == "SIGNAL"]
    assert len(sig) == len(set(sig))


@pytest.fixture(scope="module")
def synth_result_v0(tmp_path_factory):
    cfg = cfg_with_policies(tmp_path_factory.mktemp("v0"))
    m1 = synth(datetime(2021, 7, 1, tzinfo=UTC), 75 * 1440, seed=7, amp=18)
    return BacktestEngine(cfg, "EURUSD", datetime(2021, 8, 5, tzinfo=UTC), datetime(2021, 9, 14, tzinfo=UTC), D(10000)).run(m1)


def test_signal_book_policies_on_reused_setup():
    from photon.strategy.entry_model import SignalBook
    from photon.tests.test_entry_model import zone
    z = zone()
    s = Setup("X", "EURUSD", z, Trend.BULL)
    s.n_signals = 1
    assert SignalBook("REJECT", "REJECT").check(s, datetime(2021, 9, 1, tzinfo=UTC))[0] == "DUPLICATE_POI"
    for pol in ("REJECT_WHILE_ACTIVE", "ALLOW", "REPLACE"):
        assert SignalBook(pol, "REJECT").check(s, datetime(2021, 9, 1, tzinfo=UTC)) is None


def test_engine_refuses_a_second_open_position_for_the_same_setup(tmp_path):
    eng, s, it = _engine_with_pending(tmp_path)
    eng._pre_step(touch_candle(eng, it, datetime(2021, 9, 1, 9, 0, tzinfo=UTC)))
    assert s.id in eng.positions
    with pytest.raises(RuntimeError):
        eng._fill_entry(s, it, touch_candle(eng, it, datetime(2021, 9, 1, 9, 1, tzinfo=UTC)), datetime(2021, 9, 1, 9, 1, tzinfo=UTC))


# ---------------- Q-V8-5: hedefler H4'te kalır ----------------
def test_v8_targets_stay_on_h4_first_h4_swing_then_next_h4_zone_and_hold_confirmation_on_h4():
    from photon.execution.management import H4_LEG, M15_LEG, ManagementParams, build_plan
    from photon.strategy.permission import TrendClass
    from photon.tests.test_management import STATES, ENTRY, STOP, px
    from photon.zones.models import Origin, Zone, ZoneKind
    cfg = v8cfg({"management_second_target": "NEXT_MID_ZONE"})
    p = ManagementParams.from_config(cfg)
    assert p.second_target == "NEXT_MID_ZONE" and ManagementParams.from_config(load_config()).second_target == "SWING_HI"
    mk = lambda zid, lo, hi, kind=ZoneKind.SUPPLY, valid=True: Zone(zid, Timeframe.H4, kind, Origin.PIVOT, "CANDLE", px(hi), px(lo), 0, 1,
                                                                     datetime(2021, 9, 1, tzinfo=UTC), caused_events=[object()] if valid else [])
    near, far = mk("near", 90, 95), mk("far", 120, 125)                 # ilk hedef M15-rolü swing = px(60); arz zonları ötesinde
    plan = build_plan(Side.LONG, TrendClass.PRO, ENTRY, STOP, STATES, [far, near, mk("bad", 100, 105, valid=False)], p)
    legs = {l.name: l for l in plan.legs}
    assert legs[M15_LEG].price == px(60) and legs[M15_LEG].pct == 60
    assert legs[H4_LEG].price == px(90) and legs[H4_LEG].pct == 20 and legs[H4_LEG].hold_requires == "H4_CHOCH"     # en yakın geçerli zonun yakın kenarı
    none = build_plan(Side.LONG, TrendClass.PRO, ENTRY, STOP, STATES, [], p)                                      # sonraki hedef yok → %20 ilk hedefe
    assert H4_LEG not in {l.name for l in none.legs} and {l.name: l for l in none.legs}[M15_LEG].pct == 80
    assert profile_from_config(v8cfg()).hold_tf is Timeframe.H4 and profile_from_config(load_config()).hold_tf is Timeframe.H4


def test_period_diagnostics_has_funnel_daily_trend_poi_list_and_traces():
    from photon.backtest.report import period_diagnostics
    res, *_ = _scenario("REJECT")
    txt = period_diagnostics(res, datetime(2021, 8, 20, tzinfo=UTC), datetime(2021, 9, 1, tzinfo=UTC))
    for part in ("1. Dönem içi huni", "2. Gün gün trend", "3. Dönemde yaşayan POI", "4. Kurulum izleri", "D1 ", "H4 "):
        assert part in txt
    assert any(d0 <= datetime(2021, 8, 25, tzinfo=UTC) for d0, _ in res.trend_log) and res.trend_log
    assert "icra iç trend" in txt


# ---------------- PD-R003 rol bağı (V8: orta rol = H4) ----------------
def test_v8_range_filter_state_is_the_h4_swing_range_and_diag_says_so(v8_run):
    from photon.structure import pd as PD
    e, res, m1, cfg = v8_run
    r = e.runner
    assert r.model.poi_p.range_tf is Timeframe.M15                                       # config anahtarı ROL adıdır (M15 = orta rol)
    mid, hi = r._states[Timeframe.M15], r._states[Timeframe.H4]
    assert PD.swing_range(mid) == PD.swing_range(r.struct[Timeframe.H4].state())          # V8: filtre H4 swing aralığını kullanır
    assert PD.swing_range(hi) == PD.swing_range(r.struct[Timeframe.D1].state())
    assert r.model.role_names == {Timeframe.H4: "D1", Timeframe.M15: "H4"}
    texts = [rec[3] for s in res.setups for rec in s.trace if rec[1] == "GATE_FAIL:range_filter" and "range_low" in rec[3]]
    assert texts and all("range_tf=M15(rol→H4 swing aralığı)" in t for t in texts)


def test_v0_range_filter_state_is_m15_swing_range(tmp_path):
    from photon.structure import pd as PD
    cfg = cfg_with_policies(tmp_path)
    r = StrategyRunner(cfg, "EURUSD", datetime(2021, 8, 30, tzinfo=UTC), D(10000))
    for q in synth(datetime(2021, 8, 2, tzinfo=UTC), 31 * 1440, seed=3):
        r.on_m1(q)
    assert PD.swing_range(r._states[Timeframe.M15]) == PD.swing_range(r.struct[Timeframe.M15].state())
    assert r.model.role_names == {Timeframe.D1: "D1", Timeframe.H4: "H4", Timeframe.M15: "M15"}


# ---------------- zon→BOS izleme aracı ----------------
def test_trace_explanations_and_event_trace():
    from photon.zones.trace import explain_pivot, explain_range
    def c(i, o, h, l, cl):
        f = lambda x: D(str(x))
        return Candle("EURUSD", Timeframe.H4, datetime(2021, 9, 1, tzinfo=UTC) + timedelta(hours=4 * i), f(o), f(h), f(l), f(cl), True)
    pip = D("0.00001")
    # bearish, bullish(ara; yutmuyor), bullish kopuş → kopuş mumunun hemen önceki mumu karşı yönlü değil → koşu YOK
    cs = [c(0, 1.1800, 1.1805, 1.1790, 1.1795), c(1, 1.1795, 1.1810, 1.1793, 1.1805), c(2, 1.1805, 1.1850, 1.1804, 1.1848)]
    assert "koşu YOK" in explain_pivot(cs, 2, pip)
    # bearish + yutan bullish → zon
    cs2 = [c(0, 1.1800, 1.1805, 1.1790, 1.1795), c(1, 1.1795, 1.1850, 1.1793, 1.1848)]
    assert "koşu 1 mum" in explain_pivot(cs2, 1, pip) or "koşu ≥" in explain_pivot(cs2, 1, pip)
    assert "yeterli geçmiş" in explain_range(cs2, 1, pip, 3)


def test_trace_bos_cli_end_to_end(tmp_path, capsys):
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
    out = tmp_path / "t.txt"
    rc = main(["trace-bos", "--config", str(cfgp), "--tf", "M15", "--start", "2021-09-01", "--end", "2021-09-05", "--type", "BOTH",
               "--max-events", "3", "--out", str(out)])
    cap = capsys.readouterr().out
    assert rc == 0 and "Q-Z5 penceresi" in cap and "-- mumlar --" in cap and "sonuç: bu olaya bağlı zonlar" in cap
    assert out.read_text(encoding="utf-8").startswith(cap.split("\n")[0])


# ---------------- range_inside_rule (WICK | CLOSE) — H4 1048..1052 örneğinin sentetik kopyası ----------------
def _h4(i, o, h, l, c):
    f = lambda x: D(str(x))
    return Candle("EURUSD", Timeframe.H4, datetime(2021, 8, 31, 17, tzinfo=UTC) + timedelta(hours=4 * i), f(o), f(h), f(l), f(c), True)


SWEEP_CHAIN = [_h4(0, 1.18050, 1.18130, 1.17978, 1.18020),     # mother (1048)
               _h4(1, 1.18020, 1.18100, 1.17990, 1.18060),     # 1049
               _h4(2, 1.18060, 1.18110, 1.17995, 1.18040),     # 1050
               _h4(3, 1.18040, 1.18090, 1.17935, 1.18054),     # 1051: fitil mother low'un altında, kapanış içeride
               _h4(4, 1.18054, 1.18300, 1.18040, 1.18250)]     # 1052: mother high'ın üstünde KAPANIŞ → kopuş


def test_range_inside_rule_wick_gives_no_zone_close_gives_demand_zone_with_extended_wick_and_sweep_flag():
    from photon.zones.detect import range_zone
    pip = D("0.00001")
    assert range_zone(SWEEP_CHAIN, 4, pip, 3, None, "WICK") is None                                  # mevcut kural: 1051 zinciri kırar
    g = range_zone(SWEEP_CHAIN, 4, pip, 3, None, "CLOSE")
    assert (g.kind.value, g.bottom, g.top, g.first_index, g.swept) == ("DEMAND", D("1.17935"), D("1.18130"), 0, True)   # sınır en uç fitile genişler
    assert range_zone(SWEEP_CHAIN, 4, pip, 3) is None                                                # varsayılan WICK
    with pytest.raises(ValueError):
        range_zone(SWEEP_CHAIN, 4, pip, 3, None, "XX")


def test_close_rule_requires_closes_inside_and_exit_only_by_close():
    from photon.zones.detect import range_zone
    pip = D("0.00001")
    bad_close = list(SWEEP_CHAIN)
    bad_close[3] = _h4(3, 1.18040, 1.18200, 1.17935, 1.18140)       # 1051 KAPANIŞ mother high'ın üstünde → zincir kırılır
    assert range_zone(bad_close, 4, pip, 3, None, "CLOSE") is None
    no_exit = list(SWEEP_CHAIN)
    no_exit[4] = _h4(4, 1.18054, 1.18300, 1.18040, 1.18100)          # kapanış mother aralığında → kopuş yok (fitil yetmez)
    assert range_zone(no_exit, 4, pip, 3, None, "CLOSE") is None
    # fitil taşmayan klasik zincir: CLOSE sonucu WICK ile aynı sınırlar, sweep etiketi yok
    plain = [_h4(0, 1.1805, 1.1813, 1.1798, 1.1802), _h4(1, 1.1802, 1.1810, 1.1799, 1.1806), _h4(2, 1.1806, 1.1811, 1.1800, 1.1804),
             _h4(3, 1.1804, 1.1830, 1.1803, 1.1825)]
    w, c = range_zone(plain, 3, pip, 3, None, "WICK"), range_zone(plain, 3, pip, 3, None, "CLOSE")
    assert (w.bottom, w.top) == (c.bottom, c.top) and w.swept is False and c.swept is False


def test_zone_engine_labels_sweep_zone_and_config_option():
    from photon.structure import StructureEngine, StructureParams
    from photon.zones.engine import ZoneEngine, ZoneParams
    cfg = load_config()
    assert cfg.get("range_inside_rule") == "WICK" and ZoneParams.from_config(cfg, "EURUSD", Timeframe.H4).inside_rule == "WICK"
    ccfg = apply_overrides(cfg, {"range_inside_rule": "CLOSE"})
    zp = ZoneParams.from_config(ccfg, "EURUSD", Timeframe.H4)
    assert zp.inside_rule == "CLOSE"
    for rule, expect in (("WICK", 0), ("CLOSE", 1)):
        st = StructureEngine(Timeframe.H4, StructureParams.from_config(cfg, "EURUSD", Timeframe.H4))
        ze = ZoneEngine(Timeframe.H4, dataclasses.replace(zp, inside_rule=rule), st)
        for c in SWEEP_CHAIN:
            ze.update(c, [])
        rng = [z for z in ze.zones if z.origin.value == "RANGE"]
        assert len(rng) == expect
        if rng:
            assert rng[0].is_sweep is True and ze.sweep_flag(rng[0]) is True and (rng[0].bottom, rng[0].top) == (D("1.17935"), D("1.18130"))
    with pytest.raises(Exception):
        apply_overrides(cfg, {"range_inside_rule": "XX"}).require("zones")


# ---------------- aynı giriş kutusu: tek sinyal; kutu kimliği gerçek TF ----------------
def test_same_entry_box_gives_one_signal_best_score_wins_and_losers_are_reported():
    from photon.tests.test_entry_model import two_setups
    s1, s2, out = two_setups(dup="ALLOW")
    sig = [e for e in out if e.kind == "SIGNAL"]
    rej = [e for e in out if e.kind == "REJECTED"]
    assert len(sig) == 1 and len(rej) == 1 and rej[0].reason.startswith("SAME_ENTRY_BOX(kazanan ")
    loser = rej[0].setup
    winner = sig[0].setup
    assert loser is not winner and winner.state is State.ORDER_PENDING and loser.state is State.WATCHING and loser.n_signals == 0 and winner.n_signals == 1
    assert (loser.intent is None) and any(r.reason == "SAME_ENTRY_BOX" for r in loser.rejections)
    assert [r[1] for r in loser.trace][-1] == "SAME_ENTRY_BOX" and "SIGNAL" not in [r[1] for r in loser.trace]


def test_v8_entry_box_id_names_the_real_exec_tf():
    from photon.strategy.entry_model import reaction_box
    t0 = datetime(2021, 9, 1, 9, 0, tzinfo=UTC)
    ms = [_c(t0, 1.1, 1.1002, 1.0998, 1.1001), _c(t0 + timedelta(minutes=1), 1.1001, 1.1004, 1.0999, 1.1003)]
    m15 = [dataclasses.replace(c, tf=Timeframe.M15) for c in ms]
    z = reaction_box(m15, 0, 1, Trend.BULL)
    assert z.id.startswith("M15-V") and z.tf is Timeframe.M15
    assert reaction_box(ms, 0, 1, Trend.BULL).id.startswith("M1-V")


def test_v8_run_uses_m15_box_ids_and_unique_boxes_per_signal(v8_run):
    e, res, m1, cfg = v8_run
    sig = [ev for ev in res.events if ev.kind == "SIGNAL"]
    assert all(ev.intent.entry_zone_id.startswith(("M15-V", "M15-")) or ev.intent.entry_zone_kind == "FLIP" for ev in sig)
    # aynı adımda (aynı kutu) çoğaltılmış sinyal olmamalı: aynı zamanda üretilen sinyallerin kutuları farklıdır
    by_time = {}
    for ev in sig:
        by_time.setdefault(ev.time, []).append((ev.intent.side, ev.intent.entry, ev.intent.stop))
    assert all(len(v) == len(set(v)) for v in by_time.values())
