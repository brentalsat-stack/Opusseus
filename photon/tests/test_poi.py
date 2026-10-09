"""POI kapıları + 10 kriterli puanlama (DECISIONS §3), PD-R003 range filtresi, T-EN-01, iç içe/rafine zon."""
from datetime import datetime, timezone
from decimal import Decimal as D

import pytest

from photon.config import load_config
from photon.data import Timeframe
from photon.liquidity.levels import Level, Side, Source
from photon.liquidity.liquidation import LiquidationResult
from photon.risk.session import Decision
from photon.strategy.permission import Permission
from photon.strategy.poi import CRITERIA, POIContext, POIParams, evaluate_poi
from photon.structure import MarketState, Strength, SwingPoint, Trend
from photon.structure import pd as PD
from photon.structure.models import Kind, StructureEvent, EventType
from photon.zones.models import Origin, Zone, ZoneKind
from photon.zones.refine import contained_in, nested_parents, refined_zones

UTC = timezone.utc
T0 = datetime(2021, 9, 1, tzinfo=UTC)
BASE, PIP, PIPETTE = D("1.1000"), D("0.0001"), D("0.00001")
B, S, U = Trend.BULL, Trend.BEAR, Trend.UNDEFINED


def px(p) -> D:
    return BASE + D(str(p)) * PIP


def state(tf, trend, low=0, high=100, confirmed=True):
    sl = SwingPoint(tf, px(low), 0, Kind.LOW, Strength.STRONG if trend is B else Strength.WEAK, True)
    sh = SwingPoint(tf, px(high), 5, Kind.HIGH, Strength.WEAK if trend is B else Strength.STRONG, confirmed)
    eq = px((low + high) / 2) if confirmed else None
    return MarketState(tf, trend, sh, sl, trend, None, None, eq)


def ev(typ=EventType.BOS, d=B):
    return StructureEvent(Timeframe.M15, typ, d, px(0), 5, T0, True)


def zone(kind=ZoneKind.DEMAND, tf=Timeframe.M15, top=14, bottom=10, origin=Origin.PIVOT, **kw):
    z = Zone("z1", tf, kind, origin, "RANGE", px(top), px(bottom), 0, 1, T0)
    for k, v in kw.items():
        setattr(z, k, v)
    return z


OK_PERM = Permission(True, "PRO/PRO", "")
OK_SESS = Decision(True)
LIQ = LiquidationResult(True, "", Level(Side.LOW, px(12), 3, Source.EQ), 5, 0, 7)
PARAMS = POIParams.from_config(load_config())


def ctx(**kw):
    base = dict(direction=B, states={Timeframe.M15: state(Timeframe.M15, B), Timeframe.H4: state(Timeframe.H4, B)},
                permission=OK_PERM, session=OK_SESS, liquidation=LIQ, has_inducement=True, v_shape=True)
    return POIContext(**{**base, **kw})


def test_params_from_config_ten_criteria_and_weights():
    assert tuple(PARAMS.weights) == CRITERIA and len(CRITERIA) == 10
    assert PARAMS.weights["bos_and_flip"] == 3 and PARAMS.weights["sweep_zone"] == D("1.5")
    assert sum(PARAMS.weights.values()) == 16 and PARAMS.range_band_pct == 25 and PARAMS.range_tf is Timeframe.M15
    assert PARAMS.require_liquidation and PARAMS.range_filter_enabled


def test_all_gates_pass_and_score_with_breakdown():
    z = zone(caused_events=[ev()], is_flip=True, is_sweep=True, bottom=D(0) + px(10))        # EQ 12 → range'in alt %25'inde
    r = evaluate_poi(z, ctx(nested_parents=[zone(top=20, bottom=5, tf=Timeframe.H4)]), PARAMS)
    assert r.passed and not r.failed_gates
    got = {c.name: c.earned for c in r.criteria}
    assert got == {"bos_and_flip": True, "swing_break": True, "nested_zone": True, "pro_trend": True, "sweep_zone": True,
                   "inducement": True, "pivot_zone": True, "weak_target": True, "pd_alignment": True,
                   "corrective_or_vshape": True}
    assert r.score == r.max_score == 16 and "bos_and_flip=+3" in r.breakdown()


def test_no_threshold_gate_passing_poi_with_zero_score_still_signals():
    z = zone(origin=Origin.RANGE, caused_events=[ev(EventType.CHOCH)])
    c = ctx(has_inducement=False, v_shape=False, direction=B,
            states={Timeframe.M15: state(Timeframe.M15, S), Timeframe.H4: state(Timeframe.H4, S)})
    r = evaluate_poi(z, c, PARAMS)
    assert r.passed                                                # eşik puan yok
    by = {c.name: c.earned for c in r.criteria}
    assert by["swing_break"] is False and by["pivot_zone"] is False and by["pro_trend"] is False and by["weak_target"] is False
    assert r.score < r.max_score


def test_unknown_criteria_earn_nothing_and_are_marked():
    z = zone(caused_events=[ev()])
    r = evaluate_poi(z, ctx(has_inducement=None, v_shape=None), PARAMS)
    by = {c.name: c.earned for c in r.criteria}
    assert by["inducement"] is None and by["sweep_zone"] is None and by["corrective_or_vshape"] is None
    assert "inducement=?" in r.breakdown()


# ---------------- zorunlu kapılar ----------------
def gate(r, name):
    return next(g for g in r.gates if g.name == name)


def test_t_en_01_poi_below_m15_is_invalid():
    r = evaluate_poi(zone(tf=Timeframe.M5, caused_events=[ev()]), ctx(), PARAMS)
    assert not r.passed and not gate(r, "tf_min_m15").passed and gate(r, "tf_min_m15").rule == "POI-R004#1"
    assert evaluate_poi(zone(tf=Timeframe.H4, caused_events=[ev()]), ctx(), PARAMS).gates[0].passed


def test_gate_structure_or_flip_t_sd_01():
    r = evaluate_poi(zone(), ctx(), PARAMS)
    assert not r.passed and not gate(r, "structure_or_flip").passed
    assert gate(evaluate_poi(zone(is_flip=True), ctx(), PARAMS), "structure_or_flip").passed


def test_gate_permission_session_liquidation():
    z = zone(caused_events=[ev()])
    r = evaluate_poi(z, ctx(permission=Permission(False, "COUNTER/COUNTER", "işlem yok")), PARAMS)
    assert not gate(r, "permission").passed and gate(r, "permission").rule == "EN-R006"
    r = evaluate_poi(z, ctx(session=Decision(False, "OUT_OF_SESSION", "SS-R001")), PARAMS)
    assert not gate(r, "session").passed
    r = evaluate_poi(z, ctx(liquidation=None), PARAMS)
    assert not gate(r, "liquidation").passed and gate(r, "liquidation").reason == "NOT_EVALUATED"
    r = evaluate_poi(z, ctx(liquidation=LiquidationResult(False, "NO_SWEEP")), PARAMS)
    assert gate(r, "liquidation").reason == "NO_SWEEP"


# ---------------- PD-R003 range filtresi ----------------
@pytest.mark.parametrize("eq_pips,direction,passed,reason", [
    (10, B, True, ""), (25, B, True, ""), (25.1, B, False, "MIDDLE_OF_RANGE"), (50, B, False, "MIDDLE_OF_RANGE"),
    (90, B, False, "WRONG_SIDE_OF_RANGE"), (-5, B, True, ""),
    (90, S, True, ""), (75, S, True, ""), (74.9, S, False, "MIDDLE_OF_RANGE"), (10, S, False, "WRONG_SIDE_OF_RANGE")])
def test_range_filter_quarter_bands(eq_pips, direction, passed, reason):
    st = state(Timeframe.M15, B, 0, 100)
    kind = ZoneKind.DEMAND if direction is B else ZoneKind.SUPPLY
    z = zone(kind=kind, top=eq_pips + 1, bottom=eq_pips - 1)
    r = PD.range_filter(direction, z.eq, st, D(25))
    assert (r.passed, r.reason) == (passed, reason)


def test_range_unknown_fails_closed_and_can_be_disabled():
    unconf = state(Timeframe.M15, B, confirmed=False)
    z = zone(caused_events=[ev()])
    r = evaluate_poi(z, ctx(states={Timeframe.M15: unconf, Timeframe.H4: state(Timeframe.H4, B)}), PARAMS)
    assert not gate(r, "range_filter").passed and "RANGE_UNKNOWN" in gate(r, "range_filter").reason
    off = POIParams(PARAMS.weights, False, D(25), Timeframe.M15, True)
    assert gate(evaluate_poi(z, ctx(states={Timeframe.M15: unconf, Timeframe.H4: state(Timeframe.H4, B)}), off), "range_filter").passed


def test_range_filter_uses_configured_range_tf_state():
    z = zone(caused_events=[ev()], top=51, bottom=49)                                    # M15 range'inin ortası
    r = evaluate_poi(z, ctx(), PARAMS)
    assert not gate(r, "range_filter").passed and "50.0%" in gate(r, "range_filter").reason
    h4 = POIParams(PARAMS.weights, True, D(25), Timeframe.H4, True)
    wide = ctx(states={Timeframe.M15: state(Timeframe.M15, B), Timeframe.H4: state(Timeframe.H4, B, 0, 400)})
    assert gate(evaluate_poi(z, wide, h4), "range_filter").passed                         # 4H range'inde alt %25'te


# ---------------- puan kriterleri ayrıntı ----------------
def earned(r, name):
    return next(c.earned for c in r.criteria if c.name == name)


def test_pd_alignment_requires_both_m15_and_h4_and_unknown_gives_none():
    z = zone(top=11, bottom=9, caused_events=[ev()])                                      # EQ 10: ikisinde de discount
    assert earned(evaluate_poi(z, ctx(), PARAMS), "pd_alignment") is True
    h4_premium = ctx(states={Timeframe.M15: state(Timeframe.M15, B), Timeframe.H4: state(Timeframe.H4, B, 0, 15)})   # EQ 7.5 < 10 → premium
    assert earned(evaluate_poi(z, h4_premium, PARAMS), "pd_alignment") is False
    unk = ctx(states={Timeframe.M15: state(Timeframe.M15, B, confirmed=False), Timeframe.H4: state(Timeframe.H4, B)})
    assert earned(evaluate_poi(z, unk, PARAMS), "pd_alignment") is None


def test_pro_trend_needs_both_and_mixed_is_not_pro():
    z = zone(caused_events=[ev()])
    mixed = ctx(states={Timeframe.M15: state(Timeframe.M15, S), Timeframe.H4: state(Timeframe.H4, B)})
    assert earned(evaluate_poi(z, mixed, PARAMS), "pro_trend") is False
    assert earned(evaluate_poi(z, ctx(), PARAMS), "pro_trend") is True


def test_nested_zone_only_for_m15_and_pivot_vs_range_vs_flip_origin():
    parents = [zone(top=20, bottom=5, tf=Timeframe.H4)]
    assert earned(evaluate_poi(zone(caused_events=[ev()]), ctx(nested_parents=parents), PARAMS), "nested_zone") is True
    assert earned(evaluate_poi(zone(tf=Timeframe.H4, caused_events=[ev()]), ctx(nested_parents=parents), PARAMS), "nested_zone") is False
    assert earned(evaluate_poi(zone(origin=Origin.FLIP, is_flip=True), ctx(), PARAMS), "pivot_zone") is False


def test_swing_break_internal_choch_is_not_swing():
    assert earned(evaluate_poi(zone(caused_events=[ev(EventType.CHOCH)]), ctx(), PARAMS), "swing_break") is False
    assert earned(evaluate_poi(zone(caused_events=[ev(EventType.CHOCH), ev(EventType.BOS)]), ctx(), PARAMS), "swing_break") is True


def test_weak_target_depends_on_trend_in_trade_direction():
    z = zone(caused_events=[ev()])
    bear = ctx(states={Timeframe.M15: state(Timeframe.M15, S), Timeframe.H4: state(Timeframe.H4, S)})
    assert earned(evaluate_poi(z, bear, PARAMS), "weak_target") is False          # long ama iki TF de bearish
    short = ctx(direction=S, states={Timeframe.M15: state(Timeframe.M15, S), Timeframe.H4: state(Timeframe.H4, B)})
    assert earned(evaluate_poi(zone(kind=ZoneKind.SUPPLY, caused_events=[ev(d=S)]), short, PARAMS), "weak_target") is True


# ---------------- iç içe / rafine ----------------
def test_nested_and_refined_geometry():
    h4 = zone(tf=Timeframe.H4, top=30, bottom=0, caused_events=[ev()])
    m15 = zone(top=20, bottom=10, caused_events=[ev()])
    out = zone(top=35, bottom=25, caused_events=[ev()])
    sup = zone(kind=ZoneKind.SUPPLY, top=20, bottom=10, caused_events=[ev(d=S)])
    assert contained_in(m15, h4, PIPETTE) and not contained_in(out, h4, PIPETTE) and not contained_in(sup, h4, PIPETTE)
    assert nested_parents(m15, [h4, out], PIPETTE) == [h4]
    assert refined_zones(h4, [m15, out, sup], PIPETTE) == [m15]
    invalid = zone(top=20, bottom=10)                                    # SD-R005 geçersiz → rafine sayılmaz
    assert refined_zones(h4, [invalid], PIPETTE) == []
    h4.invalidated_index = 3
    assert nested_parents(m15, [h4], PIPETTE) == []                       # kullanılamaz üst zon
