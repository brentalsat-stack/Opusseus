"""MG-R001..R005, T-MG-01, T-MG-02, D-26 tutma onayı, DECISIONS §5 hacim dağılımları, sinyal çıktısı."""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.config import load_config
from photon.data import Candle, Timeframe
from photon.execution.management import (CT_LEG, H4_LEG, M15_LEG, RANGE_LEG, RISK_REMOVAL, ManagementParams, build_plan,
                                         h4_choch_since, split_lots)
from photon.execution.position import PositionManager
from photon.risk.stops import Rejected, Side
from photon.signals.output import SignalPublisher, format_cancel, format_signal
from photon.strategy.entry_model import SignalEvent
from photon.strategy.permission import TrendClass
from photon.strategy.state_machine import Setup
from photon.structure import MarketState, Strength, SwingPoint, Trend
from photon.structure.models import EventType, Kind, StructureEvent
from photon.zones.models import Origin, Zone, ZoneKind

UTC = timezone.utc
BASE, PIP = D("1.1000"), D("0.0001")
T0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
CFG = load_config()
P = ManagementParams.from_config(CFG)
B, S = Trend.BULL, Trend.BEAR


def px(p) -> D:
    return BASE + D(str(p)) * PIP


def st(tf, trend, low, high):
    sl = SwingPoint(tf, px(low), 0, Kind.LOW, Strength.STRONG if trend is B else Strength.WEAK, True)
    sh = SwingPoint(tf, px(high), 5, Kind.HIGH, Strength.WEAK if trend is B else Strength.STRONG, True)
    return MarketState(tf, trend, sh, sl, trend, None, None, None)


STATES = {Timeframe.M15: st(Timeframe.M15, B, 0, 60), Timeframe.H4: st(Timeframe.H4, B, -40, 120)}
ENTRY, STOP = px(10), px(8)                     # 2 pip risk → 4R = +8 pip → px(18)


def cd(i, h, l, c=None) -> Candle:
    h, l = D(str(h)), D(str(l))
    c = (h + l) / 2 if c is None else D(str(c))
    return Candle("EURUSD", Timeframe.M1, T0 + timedelta(minutes=i), px(c), px(max(h, c)), px(min(l, c)), px(c), True)


def mgr(spread="0.4"):
    return PositionManager(P, D(spread) * PIP, D("0.01"), D("0.01"))


def pro_plan(side=Side.LONG):
    return build_plan(Side.LONG, TrendClass.PRO, ENTRY, STOP, STATES, [], P)


def test_params_from_config_decision_values():
    assert (P.partial_pct, P.partial_at_r, P.pt_m15_pct, P.pt_h4_pct, P.ct_pct, P.range_pct) == (20, 4, 60, 20, 80, 100)
    assert P.swing_hold == "H4_CHOCH" and P.removal_method == "PARTIAL"


def test_invalid_allocations_and_unsupported_methods_rejected():
    kw = dict(removal_method="PARTIAL", partial_pct=D(20), partial_at_r=D(4), pt_m15_pct=D(60), pt_h4_pct=D(20),
              ct_pct=D(80), range_pct=D(100), swing_hold="H4_CHOCH")
    with pytest.raises(ValueError):
        ManagementParams(**{**kw, "pt_h4_pct": D(25)})
    with pytest.raises(ValueError):
        ManagementParams(**{**kw, "ct_pct": D(70)})
    with pytest.raises(NotImplementedError):
        ManagementParams(**{**kw, "removal_method": "BE_AT_FIRST_EXEC_BOS"})
    with pytest.raises(NotImplementedError):
        ManagementParams(**{**kw, "swing_hold": "M15_CHOCH"})


# ---------------- hedef planları ----------------
def test_pro_trend_plan_20_at_4r_60_m15_20_h4():
    plan = pro_plan()
    assert [(l.name, l.pct, l.price) for l in plan.legs] == [
        (RISK_REMOVAL, 20, px(18)), (M15_LEG, 60, px(60)), (H4_LEG, 20, px(120))]
    assert plan.legs[-1].hold_requires == "H4_CHOCH" and plan.first_target.name == M15_LEG
    assert plan.trend_class == "PRO"


def test_mixed_is_managed_like_pro_trend_q_p6():
    plan = build_plan(Side.LONG, TrendClass.MIXED, ENTRY, STOP, STATES, [], P)
    assert [(l.name, l.pct) for l in plan.legs] == [(RISK_REMOVAL, 20), (M15_LEG, 60), (H4_LEG, 20)] and plan.trend_class == "MIXED"


def test_counter_trend_plan_20_at_4r_80_first_m15_target_zone_or_swing():
    sup = Zone("s", Timeframe.M15, ZoneKind.SUPPLY, Origin.PIVOT, "RANGE", px(45), px(40), 0, 1, T0)
    sup.caused_events = [StructureEvent(Timeframe.M15, EventType.BOS, S, px(0), 5, T0, True)]
    plan = build_plan(Side.LONG, TrendClass.COUNTER_HTF, ENTRY, STOP, STATES, [sup], P)
    assert [(l.name, l.pct, l.price) for l in plan.legs] == [(RISK_REMOVAL, 20, px(18)), (CT_LEG, 80, px(40))]   # arz zonu swing'den (60) yakın
    plan2 = build_plan(Side.LONG, TrendClass.COUNTER_HTF, ENTRY, STOP, STATES, [], P)
    assert plan2.legs[-1].price == px(60)


def test_short_plan_mirrors():
    states = {Timeframe.M15: st(Timeframe.M15, S, 0, 60), Timeframe.H4: st(Timeframe.H4, S, -40, 120)}
    plan = build_plan(Side.SHORT, TrendClass.PRO, px(50), px(52), states, [], P)
    assert [(l.name, l.price) for l in plan.legs] == [(RISK_REMOVAL, px(42)), (M15_LEG, px(0)), (H4_LEG, px(-40))]


def test_mg_r005_no_exit_plan_is_rejected():
    no_m15 = {Timeframe.M15: st(Timeframe.M15, B, 0, 5), Timeframe.H4: STATES[Timeframe.H4]}          # M15 swing hedefi girişin altında
    r = build_plan(Side.LONG, TrendClass.PRO, ENTRY, STOP, no_m15, [], P)
    assert isinstance(r, Rejected) and r.reason == "NO_EXIT_PLAN" and r.rule == "MG-R005"
    assert isinstance(build_plan(Side.LONG, TrendClass.COUNTER_HTF, px(70), px(68), STATES, [], P), Rejected)


def test_missing_h4_target_merges_20_into_m15_leg_with_note():
    states = {Timeframe.M15: STATES[Timeframe.M15], Timeframe.H4: st(Timeframe.H4, B, -40, 5)}
    plan = build_plan(Side.LONG, TrendClass.PRO, ENTRY, STOP, states, [], P)
    assert [(l.name, l.pct) for l in plan.legs] == [(RISK_REMOVAL, 20), (M15_LEG, 80)] and plan.notes


def test_range_plan_only_when_extremes_given_remaining_volume_at_range_end_q_m2():
    plan = build_plan(Side.LONG, TrendClass.PRO, ENTRY, STOP, STATES, [], P, range_extremes=(px(-5), px(30)))
    assert [(l.name, l.pct, l.price) for l in plan.legs] == [(RISK_REMOVAL, 20, px(18)), (RANGE_LEG, 80, px(30))] and plan.trend_class == "RANGE"


# ---------------- lot bölme ----------------
def test_split_lots_round_down_and_remainder_to_last():
    assert split_lots(D("5.00"), [D(20), D(60), D(20)], D("0.01"), D("0.01")) == [D("1.00"), D("3.00"), D("1.00")]
    got = split_lots(D("0.33"), [D(20), D(60), D(20)], D("0.01"), D("0.01"))
    assert got == [D("0.06"), D("0.19"), D("0.08")] and sum(got) == D("0.33")                   # aşağı yuvarla; kalan sonda
    tiny = split_lots(D("0.03"), [D(20), D(60), D(20)], D("0.01"), D("0.01"))
    assert sum(tiny) == D("0.03") and all(x == 0 or x >= D("0.01") for x in tiny)               # min lot altı birleşir
    assert split_lots(D("0.01"), [D(20), D(60), D(20)], D("0.01"), D("0.01")) == [D(0), D(0), D("0.01")]


# ---------------- T-MG-01 / T-MG-02 ----------------
def open_pos(lots="5.00", plan=None):
    return mgr().open("x", Side.LONG, ENTRY, STOP, D(lots), plan or pro_plan(), T0)


def test_t_mg_01_20_percent_at_4r_stop_stays_and_stop_out_nets_zero_r():
    m, pos = mgr(), None
    pos = m.open("x", Side.LONG, ENTRY, STOP, D("5.00"), pro_plan(), T0)
    f = m.on_candle(pos, cd(1, 18.2, 12), T0)                                        # 4R'ye dokundu
    assert [(x.leg, x.lots, x.r) for x in f] == [(RISK_REMOVAL, D("1.00"), D(4))] and pos.risk_removed and pos.lots_open == D("4.00")
    assert pos.stop == STOP                                                           # stop YERİNDE (MG-R001)
    f2 = m.on_candle(pos, cd(2, 14, 7.9), T0 + timedelta(minutes=1))                  # stop
    assert [(x.leg, x.reason) for x in f2] == [("STOP", "SL_AFTER_RISK_REMOVAL")] and pos.closed
    assert pos.realized_r == 0                                                        # 0.2×4R − 0.8×1R = 0
    assert pos.pnl_amount(PIP, D(10)) == D(0)


def test_stop_without_risk_removal_is_minus_1r():
    m, pos = mgr(), open_pos()
    m.on_candle(pos, cd(1, 12, 7.9), T0)
    assert pos.realized_r == D(-1) and pos.closed and pos.fills[0].reason == "SL"


def test_t_mg_02_scale_in_rejected_until_risk_removed_mg_r004():
    m, pos = mgr(), open_pos()
    d = m.request_scale_in(pos)
    assert not d.allowed and d.reason == "RISK_NOT_REMOVED" and d.rule == "MG-R004"
    m.on_candle(pos, cd(1, 18.2, 12), T0)
    assert m.request_scale_in(pos).allowed
    m.on_candle(pos, cd(2, 14, 7.9), T0)
    assert m.request_scale_in(pos).reason == "POSITION_CLOSED"


def test_full_pro_trend_run_with_4h_choch_confirmation_pays_4r_8_6_r_and_closes():
    m, pos = mgr(), open_pos()
    m.on_candle(pos, cd(1, 19, 12), T0)                                               # 4R
    f = m.on_candle(pos, cd(2, 61, 15), T0, h4_choch_confirmed=True)                  # M15 hedefi: %60; son %20 tutulur
    assert [x.leg for x in f] == [M15_LEG] and pos.lots_open == D("1.00") and not pos.closed
    f = m.on_candle(pos, cd(3, 121, 60), T0, h4_choch_confirmed=True)
    assert [x.leg for x in f] == [H4_LEG] and pos.closed
    # R: 0.2×4 + 0.6×25 + 0.2×55 = 0.8 + 15 + 11 = 26.8 (hedefler 8 / 50 / 110 pip uzakta, risk 2 pip)
    assert pos.realized_r == D("26.8")


def test_d26_without_4h_choch_last_20_percent_closes_at_m15_target():
    m, pos = mgr(), open_pos()
    m.on_candle(pos, cd(1, 19, 12), T0)
    f = m.on_candle(pos, cd(2, 61, 15), T0, h4_choch_confirmed=False)
    assert [x.leg for x in f] == [M15_LEG, "NO_HOLD_CONFIRMATION"] and pos.closed and f[1].price == px(60)
    assert pos.realized_r == D("0.2") * 4 + D("0.8") * 25


def test_same_candle_stop_and_target_counts_as_stop_and_is_reported():
    m, pos = mgr(), open_pos()
    f = m.on_candle(pos, cd(1, 19, 7.5), T0)                                          # hem 4R hem stop
    assert [x.leg for x in f] == ["STOP"] and pos.realized_r == D(-1) and m.stats["same_candle_stop_first"] == 1
    assert "SAME_CANDLE_STOP_FIRST" in pos.notes[0]


def test_same_candle_stop_after_prior_removal_counts_too():
    m, pos = mgr(), open_pos()
    m.on_candle(pos, cd(1, 19, 12), T0)
    m.on_candle(pos, cd(2, 61, 7.5), T0)                                              # M15 hedefi + stop aynı mumda → stop
    assert pos.realized_r == 0 and m.stats["same_candle_stop_first"] == 1


def test_spread_matters_for_short_exits_ask_vs_bid_and_long_uses_bid():
    m = mgr("0.4")
    pos = m.open("s", Side.SHORT, px(50), px(52), D("1.00"), build_plan(Side.SHORT, TrendClass.PRO, px(50), px(52),
                 {Timeframe.M15: st(Timeframe.M15, S, 0, 60), Timeframe.H4: st(Timeframe.H4, S, -40, 120)}, [], P), T0)
    assert m.on_candle(pos, cd(1, 51.5, 43), T0) == []                                # bid high 51.5 + 0.4 < 52 stop; low 43+0.4 > 42 → 4R yok
    assert m.on_candle(pos, cd(2, 51.5, 41.5), T0)[0].leg == RISK_REMOVAL             # ask low 41.9 ≤ 42 (ask high 51.9 < 52)
    assert m.on_candle(pos, cd(3, 51.7, 45), T0)[0].leg == "STOP"                     # ask high 52.1 ≥ 52
    pl = open_pos()
    assert mgr().on_candle(pl, cd(1, 17.9, 12), T0) == []                             # long: bid high 17.9 < 18 → 4R yok (spread çıkışı etkilemez)


def test_h4_choch_since_helper_d26():
    def e(minute, d=B, warm=False, typ=EventType.CHOCH):
        return StructureEvent(Timeframe.H4, typ, d, px(1), 3, T0 + timedelta(minutes=minute), False, warmup=warm)
    assert h4_choch_since([e(5)], B, T0) and not h4_choch_since([e(0)], B, T0)       # girişten SONRA
    assert not h4_choch_since([e(5, d=S)], B, T0) and not h4_choch_since([e(5, warm=True)], B, T0)
    assert not h4_choch_since([e(5, typ=EventType.BOS)], B, T0)


# ---------------- sinyal çıktısı ----------------
def intent_for_output():
    from photon.tests.test_entry_model import build, run_path, make_choch, with_zones, zone as ezone, bos as ebos
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    with_zones(ze1, ch)
    s, out, _ = run_path(em, ze1, m1s, states, ezone(caused_events=[ebos()]), ze15, choch=ch)
    return next(e for e in out if e.kind == "SIGNAL")


def test_signal_text_contains_all_required_fields_turkish_istanbul_time():
    ev = intent_for_output()
    txt = format_signal(ev.intent)
    for needle in ("PHOTON SİNYAL", "Europe/Istanbul", "EURUSD", "LONG", "Giriş:", "Stop:", "Lot: 5.00 (500,000 birim)", "%1 = 100.00",
                   "Hedefler:", "4.0R", "risk kaldırılır, stop yerinde", "%20", "%60", "M15 zayıf swing", "4H zayıf swing",
                   "tutma onayı: H4_CHOCH", "İptal: dolmadan", "POI puanı:", "bos_and_flip", "Trend: 4H BULL / M15 BULL (PRO)",
                   "Seans: 07:00–10:00 Europe/London (09:00–12:00 Europe/Istanbul)", "Haber:", "Kurallar:", "EN-R001", "MG-R005"):
        assert needle in txt, needle
    assert "10:11 (Europe/Istanbul)" in txt                                            # 07:11 UTC → 10:11 İstanbul (UTC+3)


def test_publisher_screen_and_log_channels_and_rejections_log_only(caplog):
    ev = intent_for_output()
    screen = []
    pub = SignalPublisher(["SCREEN", "LOG_FILE"], printer=screen.append)
    with caplog.at_level(logging.INFO, logger="photon.signal"):
        text = pub.publish(ev)
        assert pub.publish(SignalEvent("REJECTED", ev.setup, ev.time, reason="GATE:x")) is None
        cancel = pub.publish(SignalEvent("CANCELLED", ev.setup, ev.time, ev.intent, "FIRST_TARGET_REACHED_BEFORE_FILL"))
    assert screen == [text, cancel] and "PHOTON SİNYAL" in caplog.text and "PHOTON İPTAL" in caplog.text and "RET" in caplog.text
    only_log = SignalPublisher(["LOG_FILE"], printer=screen.append)
    n = len(screen)
    only_log.publish(ev)
    assert len(screen) == n
    with pytest.raises(ValueError):
        SignalPublisher(["EMAIL"])


def test_publisher_from_config_uses_notifications_and_display_tz():
    pub = SignalPublisher.from_config(CFG, printer=lambda s: None)
    assert pub.channels == {"SCREEN", "LOG_FILE"} and pub.tz.key == "Europe/Istanbul"


def test_setup_state_follows_position_lifecycle_risk_free_then_closed():
    from photon.tests.test_entry_model import build, run_path, make_choch, with_zones, zone as ezone, bos as ebos
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    with_zones(ze1, ch)
    s, out, _ = run_path(em, ze1, m1s, states, ezone(caused_events=[ebos()]), ze15, choch=ch)
    sig = next(e for e in out if e.kind == "SIGNAL").intent
    m = mgr()
    pos = m.open(s.id, sig.side, sig.entry, sig.stop, sig.lots, sig.plan, T0)
    em.mark_filled(s, T0)
    fills = m.on_candle(pos, cd(1, float((sig.plan.legs[0].price - BASE) / PIP) + 0.1, 16), T0)
    assert fills and pos.risk_removed
    em.mark_risk_free(s, T0)
    assert s.state.value == "RISK_FREE" and m.request_scale_in(pos).allowed
    m.on_candle(pos, cd(2, 17, float((sig.stop - BASE) / PIP) - 0.1), T0)
    assert pos.closed and pos.realized_r == 0
    assert em.mark_closed(s, T0, pos.pnl_amount(PIP, D(10))).value == "WATCHING"        # net 0 → kayıp sayılmaz (Q-P3)
    assert em.tracker.losses(T0) == 0
