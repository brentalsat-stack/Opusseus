"""EN-R001 giriş modeli + FINAL_SPEC §17 durum makinesi. T-EN-05, T-EN-06, T-DUP-01, T-EN-01 (POI kapısı), iptal, D-02, EN-R007, Q-P1.
Senaryo: LONG, talep POI [10..14 pip] (M15, geçerli), M1 inişi eşit dipleri süpürüp POI'ye dokunur, M1 CHoCH + flip zonu → limit sinyal."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.config import load_config
from photon.data import Candle, Timeframe
from photon.risk.limits import DayLossTracker
from photon.risk.session import SessionClock
from photon.risk.sizing import SizingParams
from photon.risk.stops import Side, StopParams
from photon.execution.management import ManagementParams
from photon.strategy.entry_model import (EntryModel, EntryParams, MarketView, choose_entry_zone, double_bos, reaction_box, fill_touch,
                                         first_target, visit_start)
from photon.strategy.permission import TrendClass
from photon.strategy.poi import POIParams
from photon.strategy.state_machine import ALLOWED, IllegalTransition, Setup, State, global_state
from photon.structure import MarketState, Strength, StructureEngine, StructureParams, SwingPoint, Trend
from photon.structure.models import EventType, Kind, StructureEvent
from photon.zones.engine import ZoneEngine, ZoneParams
from photon.zones.models import Origin, Zone, ZoneKind

UTC = timezone.utc
BASE, PIP, PIPETTE = D("1.1000"), D("0.0001"), D("0.00001")
B, S = Trend.BULL, Trend.BEAR
T0 = datetime(2021, 9, 1, 7, 0, tzinfo=UTC)          # 08:00 Londra (yaz), seans içi
CFG = load_config()


def px(p) -> D:
    return BASE + D(str(p)) * PIP


def m1c(i, h, l, c=None) -> Candle:
    h, l = D(str(h)), D(str(l))
    c = (h + l) / 2 if c is None else D(str(c))
    return Candle("EURUSD", Timeframe.M1, T0 + timedelta(minutes=i), px(c), px(max(h, c)), px(min(l, c)), px(c), True)


def state(tf, trend, low=0, high=100):
    sl = SwingPoint(tf, px(low), 0, Kind.LOW, Strength.STRONG if trend is B else Strength.WEAK, True)
    sh = SwingPoint(tf, px(high), 5, Kind.HIGH, Strength.WEAK if trend is B else Strength.STRONG, True)
    return MarketState(tf, trend, sh, sl, trend, None, None, px((low + high) / 2))


def bos(d=B, tf=Timeframe.M15, minute=0):
    return StructureEvent(tf, EventType.BOS, d, px(0), 5, T0 - timedelta(hours=1) + timedelta(minutes=minute), True)


def zone(kind=ZoneKind.DEMAND, tf=Timeframe.M15, top=14, bottom=10, origin=Origin.PIVOT, zid="poi", **kw):
    z = Zone(zid, tf, kind, origin, "RANGE", px(top), px(bottom), 0, 1, T0 - timedelta(hours=3))
    for k, v in kw.items():
        setattr(z, k, v)
    return z


# --- M1 yol: eşit dipler (idx2, idx4) → süpürme idx6 → POI dokunuşu idx7 → toparlanma ---
M1_ROWS = [(30, 25), (28, 22), (26, 20), (27, 21), (26, 20.1), (25, 21), (23, 18), (20, 13), (16, 13.5), (17, 14.5), (19, 16)]
CHOCH_IDX = 10


def build(entry_type="CONFIRMATION", dup="REJECT", opp="REJECT", stop_mode=None, states=None, requires_sweep=False,
          tracker=None, zones_extra=None, news=None, zone_choice="FLIP_FIRST"):
    ep = EntryParams(entry_type, requires_sweep, True, True, dup, opp, 10, 2 * PIP, PIPETTE, D("0.4") * PIP, entry_zone_choice=zone_choice)
    sp = StopParams.from_config(CFG, "EURUSD")
    if stop_mode:
        sp = StopParams(sp.pip_size, stop_mode, sp.fixed_sl_pips, sp.sl_buffer_pips, sp.min_sl_pips)
    em = EntryModel("EURUSD", ep, POIParams.from_config(CFG), sp, SizingParams.from_config(CFG, "EURUSD"),
                    SessionClock.from_config(CFG), tracker or DayLossTracker.from_config(CFG), ManagementParams.from_config(CFG), news)
    st15 = StructureEngine(Timeframe.M15, StructureParams(PIP, D(15), True, 2))
    ze15 = ZoneEngine(Timeframe.M15, ZoneParams(PIP, "CANDLE", 3, D(2), D(2)), st15)
    m1s = StructureEngine(Timeframe.M1, StructureParams.internal_only_params(PIP))
    ze1 = ZoneEngine(Timeframe.M1, ZoneParams(PIP, "RANGE", 3, D(2), D(2)), m1s)
    states = states or {Timeframe.H4: state(Timeframe.H4, B), Timeframe.M15: state(Timeframe.M15, B)}
    return em, ze15, ze1, m1s, states


def run_path(em, ze1, m1s, states, poi, ze15, rows=M1_ROWS, choch=None, flip=True, extreme=True, m15_events=(),
             zones=None, balance=D(10000), start_idx=0):
    """Kurulumu oluştur ve M1 mumlarını sırayla ver. CHoCH olayı `choch` ile CHOCH_IDX'te enjekte edilir."""
    zones = zones if zones is not None else {Timeframe.M15: [poi], Timeframe.H4: [], Timeframe.D1: []}
    setup = em.watch(poi, ze15, zones)
    m1 = [m1c(i, *r) for i, r in enumerate(rows)]
    out = []
    for i, c in enumerate(m1):
        m1s.update(c)
        evs = [choch] if (choch is not None and i == CHOCH_IDX) else []
        view = MarketView(c.open_time + timedelta(minutes=1), m1, i, evs, m1s, ze1, states, list(m15_events), zones, balance)
        out += em.step(view)
    return setup, out, m1


def make_choch():
    return StructureEvent(Timeframe.M1, EventType.CHOCH, B, px(15), CHOCH_IDX, T0 + timedelta(minutes=CHOCH_IDX), False,
                          level_index=5, origin_index=7)


def with_zones(ze1, choch, flip=True, extreme=True):
    if extreme:
        ze1.zones.append(zone(tf=Timeframe.M1, top=13.5, bottom=12.5, zid="ext", caused_events=[choch]))
    if flip:
        ze1.zones.append(zone(tf=Timeframe.M1, top=17, bottom=15, origin=Origin.FLIP, zid="flip", is_flip=True,
                              caused_events=[choch]))


def test_confirmation_flow_gives_limit_signal_and_state_history():
    em, ze15, ze1, m1s, states = build()
    poi = zone(caused_events=[bos()])
    ch = make_choch()
    with_zones(ze1, ch)
    s, out, m1 = run_path(em, ze1, m1s, states, poi, ze15, choch=ch)
    (sig,) = [e for e in out if e.kind == "SIGNAL"]
    it = sig.intent
    assert s.state is State.ORDER_PENDING and it.side is Side.LONG and it.type == "LIMIT"
    assert it.entry_zone_id == "flip" and it.entry_zone_kind == "FLIP"                 # decisional_flip_requires_sweep=false → flip'ten gir
    assert it.stop == px("14.9") and it.entry == px("16.9") and it.pip_risk == D(2)    # sabit 2 pip: stop = zon dibi − 1 pipette
    assert it.lots == D("5.00") and it.units == D(500000) and it.risk_pct == D("0.01")
    assert it.cancel_if_reaches == px(100) and it.trend_class == "PRO" and "bilinmiyor" in it.news
    assert [h[2] for h in s.history] == [State.POI_MITIGATED, State.CONFIRMATION_PENDING, State.ENTRY_READY, State.ORDER_PENDING]
    assert s.mitigation_time == m1[7].open_time and s.visit_start == 7 and s.choch is ch
    assert it.poi_score > 0 and "bos_and_flip" in it.score_breakdown and "EN-R001" in it.rules


def test_t_en_05_choch_without_flip_uses_extreme_zone():
    em, ze15, ze1, m1s, states = build()
    poi = zone(caused_events=[bos()])
    ch = make_choch()
    with_zones(ze1, ch, flip=False)
    s, out, _ = run_path(em, ze1, m1s, states, poi, ze15, choch=ch)
    (sig,) = [e for e in out if e.kind == "SIGNAL"]
    assert sig.intent.entry_zone_id.startswith("M1-V") and sig.intent.entry_zone_kind == "EXTREME"     # Q-Z11: V tepki kutusu (algılanan "ext" zon DEĞİL)


def test_flip_requires_sweep_config_falls_back_to_extreme_if_flip_did_not_sweep():
    em, ze15, ze1, m1s, states = build(requires_sweep=True)
    poi = zone(caused_events=[bos()])
    ch = make_choch()
    with_zones(ze1, ch)
    flip = next(z for z in ze1.zones if z.is_flip)
    flip.is_sweep = False                                                               # sweep_flag önbelleği: sweep almadı
    s, out, _ = run_path(em, ze1, m1s, states, poi, ze15, choch=ch)
    assert next(e for e in out if e.kind == "SIGNAL").intent.entry_zone_kind == "EXTREME"
    em2, ze15b, ze1b, m1sb, states = build(requires_sweep=True)
    with_zones(ze1b, ch)
    next(z for z in ze1b.zones if z.is_flip).is_sweep = True
    _, out2, _ = run_path(em2, ze1b, m1sb, states, zone(caused_events=[bos()]), ze15b, choch=ch)
    assert next(e for e in out2 if e.kind == "SIGNAL").intent.entry_zone_kind == "FLIP"


def test_q_z11_one_candle_choch_leg_without_any_m1_zone_still_produces_v_box_entry():
    """M1 giriş kutusu zon algılamasına (SD-R001/R002) bağlı değildir: pencerede hiç M1 zonu olmasa da kutu çizilir."""
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    assert not ze1.zones
    s, out, _ = run_path(em, ze1, m1s, states, zone(caused_events=[bos()]), ze15, choch=ch)
    sig = [e for e in out if e.kind == "SIGNAL"]
    assert sig and sig[0].intent.entry_zone_kind == "EXTREME" and sig[0].intent.entry_zone_id.startswith("M1-V")
    assert s.state is State.ORDER_PENDING and not any(r.reason == "NO_ENTRY_ZONE" for r in s.rejections)


def _c(i, o, h, l, c):
    from photon.data.models import Candle
    f = lambda x: D(str(x))
    return Candle("EURUSD", Timeframe.M1, T0 + timedelta(minutes=i), px(f(o)), px(f(h)), px(f(l)), px(f(c)), True)


def test_q_z11_reaction_box_long_base_low_to_top_of_base_group_and_short_mirror():
    # long: 0 yükseliş (pencere dışı), 1-2 ardışık bearish, 3 taban (bearish, en düşük low), 4 bullish CHoCH mumu
    m1 = [_c(0, 10, 14, 9, 13), _c(1, 12, 13, 8, 9), _c(2, 9, 11, 6, 7), _c(3, 7, 8, 3, 4), _c(4, 4, 12, 4, 11)]
    z = reaction_box(m1, 1, 4, Trend.BULL)
    assert (z.bottom, z.top, z.kind, z.origin) == (px(3), px(13), ZoneKind.DEMAND, Origin.V_REACTION)    # üst = {1,2,3} grubunun en yüksek high'ı
    assert z.first_index == 1 and z.created_index == 4
    # pencere başlangıcı grubu keser: start=2 → mum 1 gruba girmez
    z2 = reaction_box(m1, 2, 4, Trend.BULL)
    assert (z2.bottom, z2.top) == (px(3), px(11))
    # taban mumu bullish ise (iğne): yalnız kendisi + doğrudan öncesindeki bearish'ler
    m2 = [_c(0, 10, 11, 8, 9), _c(1, 9, 12, 3, 11), _c(2, 11, 15, 10, 14)]
    z3 = reaction_box(m2, 0, 2, Trend.BULL)
    assert (z3.bottom, z3.top) == (px(3), px(12)) and z3.first_index == 0     # mum 0 bearish → gruba girer; high max(11,12)
    # short simetrik
    s1 = [_c(0, 10, 11, 7, 8), _c(1, 8, 9, 7, 8.5), _c(2, 8.5, 14, 8, 13), _c(3, 13, 20, 12, 19), _c(4, 19, 19, 9, 10)]
    zs = reaction_box(s1, 1, 4, Trend.BEAR)
    assert (zs.top, zs.bottom, zs.kind) == (px(20), px(7), ZoneKind.SUPPLY)
    assert reaction_box(m1, 4, 3, Trend.BULL) is None                         # geçersiz pencere
    assert reaction_box(m1, 4, 4, Trend.BULL) is not None                     # 1 mumluk bacak: CHoCH mumunun kendisi


def test_t_en_06_sl_below_2_pip_rejects_entry():
    em, ze15, ze1, m1s, states = build(stop_mode="DISTAL")
    ch = make_choch()
    ze1.zones.append(zone(tf=Timeframe.M1, top=16.5, bottom=15, origin=Origin.FLIP, zid="flip", is_flip=True, caused_events=[ch]))
    s, out, _ = run_path(em, ze1, m1s, states, zone(caused_events=[bos()]), ze15, choch=ch)      # 1.5 + 0.1 = 1.6 pip
    assert out[-1].kind == "REJECTED" and out[-1].reason == "SL_BELOW_MIN" and s.rejections[-1].rule == "SL-R003"
    assert s.state is State.WATCHING


def test_t_en_01_poi_below_m15_fails_gate_and_gate_failures_are_reported():
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    with_zones(ze1, ch)
    poi = zone(tf=Timeframe.M5, caused_events=[bos()])
    s, out, _ = run_path(em, ze1, m1s, states, poi, ze15, choch=ch, zones={Timeframe.M15: [], Timeframe.H4: [], Timeframe.D1: []})
    assert out[-1].reason == "GATE:tf_min_m15" and s.rejections[-1].rule == "POI-R004#1"


def test_range_filter_gate_blocks_middle_of_range():
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    with_zones(ze1, ch)
    poi = zone(top=54, bottom=50, caused_events=[bos()])      # M15 range [0,100]'ün ortası
    rows = [(r[0] + 40, r[1] + 40) for r in M1_ROWS]
    s, out, _ = run_path(em, ze1, m1s, states, poi, ze15, rows=rows, choch=ch)
    assert out[-1].reason == "GATE:range_filter" and "MIDDLE_OF_RANGE" in s.rejections[-1].detail


def test_liquidation_gate_missing_sweep_means_no_signal():
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    with_zones(ze1, ch)
    rows = [(30, 25), (29, 24), (28, 23), (27, 22), (26, 21), (25, 20), (24, 19), (20, 13), (16, 13.5), (17, 14.5), (19, 16)]   # düz iniş: eşit dip yok, iç referans yok
    s, out, _ = run_path(em, ze1, m1s, states, zone(caused_events=[bos()]), ze15, rows=rows, choch=ch)
    assert out[-1].reason == "GATE:liquidation" and s.rejections[-1].detail == "NO_SWEEP"


PRO_COUNTER = {Timeframe.H4: state(Timeframe.H4, B), Timeframe.M15: state(Timeframe.M15, S)}
STAY_ROWS = M1_ROWS[:8] + [(15, 12), (14.5, 11), (19, 16)]            # idx7-9 POI içinde kalır (aynı dokunuş), idx10 toparlanma


def run_with_m15(em, ze1, m1s, poi, ze15, ch, m15_event, from_idx, states=PRO_COUNTER):
    zones = {Timeframe.M15: [poi], Timeframe.H4: [], Timeframe.D1: []}
    setup = em.watch(poi, ze15, zones)
    m1 = [m1c(i, *r) for i, r in enumerate(STAY_ROWS)]
    out = []
    for i, c in enumerate(m1):
        m1s.update(c)
        evs = [ch] if i == CHOCH_IDX else []
        m15 = [m15_event] if (m15_event is not None and i >= from_idx) else []
        out += em.step(MarketView(c.open_time + timedelta(minutes=1), m1, i, evs, m1s, ze1, states, m15, zones, D(10000)))
    return setup, out


def test_t_en_02_pro_counter_without_4h_poi_is_denied():
    em, ze15, ze1, m1s, _ = build()
    ch = make_choch()
    with_zones(ze1, ch)
    s, out = run_with_m15(em, ze1, m1s, zone(caused_events=[bos()]), ze15, ch, None, 0)
    assert not [e for e in out if e.kind == "SIGNAL"] and s.rejections[0].reason == "PERMISSION"


def test_q_p1_m15_choch_after_mitigation_opens_permission_while_price_still_in_poi():
    em, ze15, ze1, m1s, _ = build()
    ch = make_choch()
    with_zones(ze1, ch)
    after = StructureEvent(Timeframe.M15, EventType.CHOCH, B, px(1), 3, T0 + timedelta(minutes=8), False)   # dokunuş 07:07 → sonra
    s, out = run_with_m15(em, ze1, m1s, zone(caused_events=[bos()]), ze15, ch, after, 8)
    assert s.rejections[0].reason == "PERMISSION"                       # idx7'de henüz CHoCH yok
    sig = next(e for e in out if e.kind == "SIGNAL")                     # idx8: aynı dokunuşta yeniden değerlendirme → izin
    assert s.mitigation_time == T0 + timedelta(minutes=7) and sig.intent.entry_zone_kind == "FLIP"
    assert "PRO/COUNTER→CHoCH" in [h[3] for h in s.history if h[2] is State.CONFIRMATION_PENDING][0]


def test_q_p1_choch_before_mitigation_does_not_count():
    em, ze15, ze1, m1s, _ = build()
    ch = make_choch()
    with_zones(ze1, ch)
    early = StructureEvent(Timeframe.M15, EventType.CHOCH, B, px(1), 3, T0 + timedelta(minutes=2), False)   # dokunuştan (07:07) önce
    s, out = run_with_m15(em, ze1, m1s, zone(caused_events=[bos()]), ze15, ch, early, 0)
    assert not [e for e in out if e.kind == "SIGNAL"]


def test_counter_htf_requires_double_bos_on_m15_en_r007():
    states = {Timeframe.H4: state(Timeframe.H4, S), Timeframe.M15: state(Timeframe.M15, B)}       # COUNTER/PRO → izinli ama karşı-HTF
    em, ze15, ze1, m1s, _ = build()
    ch = make_choch()
    with_zones(ze1, ch)
    poi = zone(caused_events=[bos()])
    s, out, _ = run_path(em, ze1, m1s, states, poi, ze15, choch=ch, m15_events=[bos()])           # tek BOS yetmez
    assert s.rejections[0].reason == "COUNTER_HTF_NEEDS_DOUBLE_BOS" and s.rejections[0].rule == "EN-R007"
    em2, ze15b, ze1b, m1sb, _ = build()
    with_zones(ze1b, ch)
    s2, out2, _ = run_path(em2, ze1b, m1sb, states, zone(caused_events=[bos()]), ze15b, choch=ch,
                           m15_events=[bos(minute=0), bos(minute=15)])
    sig = next(e for e in out2 if e.kind == "SIGNAL")
    assert sig.intent.trend_class == "COUNTER_HTF"


def test_double_bos_helper():
    assert double_bos([bos(), bos()], B) and not double_bos([bos()], B)
    assert not double_bos([bos(), bos(), bos(d=S)], B)               # karşı yönlü son BOS sayacı sıfırlar
    assert double_bos([bos(d=S), bos(), bos()], B) and not double_bos([bos(), bos()], S)


# ---------------- T-DUP-01 / karşıt sinyal politikası ----------------
def two_setups(dup="REJECT", opp="REJECT", second_kind=ZoneKind.DEMAND, second_id="poi"):
    em, ze15, ze1, m1s, states = build(dup=dup, opp=opp)
    ch = make_choch()
    with_zones(ze1, ch)
    poi1 = zone(caused_events=[bos()])
    zones = {Timeframe.M15: [poi1], Timeframe.H4: [], Timeframe.D1: []}
    s1 = em.watch(poi1, ze15, zones)
    poi2 = zone(kind=second_kind, caused_events=[bos(d=second_kind.direction)], zid=second_id, top=14, bottom=10)
    s2 = em.watch(poi2, ze15, zones)
    m1 = [m1c(i, *r) for i, r in enumerate(M1_ROWS)]
    out = []
    for i, c in enumerate(m1):
        m1s.update(c)
        evs = [ch] if i == CHOCH_IDX else []
        out += em.step(MarketView(c.open_time + timedelta(minutes=1), m1, i, evs, m1s, ze1, states, [], zones, D(10000)))
    return s1, s2, out


def test_t_dup_01_second_limit_for_same_poi_is_rejected_by_policy():
    s1, s2, out = two_setups(dup="REJECT", second_id="poi")        # aynı id → aynı POI
    # watch() her çağrıda ayrı Setup üretir; aynı POI zonu için ikisi de CHoCH'u görür: ilki sinyal, ikincisi ret
    kinds = [e.kind for e in out]
    assert kinds.count("SIGNAL") == 1 and kinds.count("REJECTED") == 1
    assert next(e for e in out if e.kind == "REJECTED").reason == "DUPLICATE_POI" and s1.state is State.ORDER_PENDING


def test_duplicate_policy_allow_and_replace():
    s1, s2, out = two_setups(dup="ALLOW")
    assert [e.kind for e in out].count("SIGNAL") == 2
    s1, s2, out = two_setups(dup="REPLACE")
    assert [e.kind for e in out].count("SIGNAL") == 2 and s1.state is State.WATCHING and s2.state is State.ORDER_PENDING


def test_opposite_signal_policy_reject_and_allow():
    # ters yönlü ikinci kurulum aynı M1 CHoCH'u (BULL) görmez; karşıt politikayı doğrudan SignalBook ile sına
    em, ze15, ze1, m1s, states = build(opp="REJECT")
    s_long = Setup("L", "EURUSD", zone(), B)
    s_long.state = State.ORDER_PENDING
    s_short = Setup("S", "EURUSD", zone(kind=ZoneKind.SUPPLY, zid="sup"), S)
    em.book.setups += [s_long, s_short]
    assert em.book.check(s_short, T0)[0] == "OPPOSITE_SIGNAL"
    em.book.opp = "ALLOW"
    assert em.book.check(s_short, T0) is None


# ---------------- iptal kuralı (DECISIONS §7) ----------------
def test_pending_limit_cancelled_when_first_target_reached_before_fill_else_ambiguous():
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    with_zones(ze1, ch)
    poi = zone(caused_events=[bos()])
    s, out, m1 = run_path(em, ze1, m1s, states, poi, ze15, choch=ch)
    zones = {Timeframe.M15: [poi], Timeframe.H4: [], Timeframe.D1: []}
    # giriş 16.9'a dokunmadan hedef 100'e ulaşan mum → iptal
    c = m1c(11, 101, 40)
    ev = em.step(MarketView(c.open_time + timedelta(minutes=1), m1 + [c], 11, [], m1s, ze1, states, [], zones, D(10000)))
    assert [e.kind for e in ev] == ["CANCELLED"] and s.state is State.WATCHING
    # aynı mumda hem giriş hem hedef: sıra bilinmiyor → iptal edilmez, not düşülür (backtest çözer)
    em2, ze15b, ze1b, m1sb, states = build()
    with_zones(ze1b, ch)
    poi2 = zone(caused_events=[bos()])
    s2, _, m1b = run_path(em2, ze1b, m1sb, states, poi2, ze15b, choch=ch)
    c2 = m1c(11, 101, 15)
    ev2 = em2.step(MarketView(c2.open_time + timedelta(minutes=1), m1b + [c2], 11, [], m1sb, ze1b, states, [],
                              {Timeframe.M15: [poi2], Timeframe.H4: [], Timeframe.D1: []}, D(10000)))
    assert ev2 == [] and s2.state is State.ORDER_PENDING and s2.notes and "AMBIGUOUS" in s2.notes[0]


def test_fill_touch_uses_ask_for_long_and_bid_for_short():
    c = m1c(0, 20, 16.8)                                        # bid low 16.8 → ask low = 17.2 (spread 0.4)
    assert fill_touch(Side.LONG, px("17.3"), c, D("0.4") * PIP)
    assert not fill_touch(Side.LONG, px("17.1"), c, D("0.4") * PIP)
    assert fill_touch(Side.SHORT, px("19.9"), c, D("0.4") * PIP) and not fill_touch(Side.SHORT, px("20.1"), c, D("0.4") * PIP)


# ---------------- oturum / gün kilidi / geçersiz POI ----------------
def test_no_progress_outside_session_and_when_day_locked():
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    with_zones(ze1, ch)
    poi = zone(caused_events=[bos()])
    setup = em.watch(poi, ze15, {Timeframe.M15: [poi], Timeframe.H4: [], Timeframe.D1: []})
    late = datetime(2021, 9, 1, 14, 0, tzinfo=UTC)          # 15:00 Londra → seans dışı
    m1 = [Candle("EURUSD", Timeframe.M1, late + timedelta(minutes=i), px(15), px(15), px(12), px(13), True) for i in range(3)]
    for i, c in enumerate(m1):
        em.step(MarketView(c.open_time + timedelta(minutes=1), m1, i, [], m1s, ze1, states, [], {}, D(10000)))
    assert setup.state is State.WATCHING and not setup.history
    # gün kilitli
    tr = DayLossTracker.from_config(CFG)
    for h in (9, 10, 11):
        tr.record_close(datetime(2021, 9, 1, h - 3, tzinfo=UTC), D("-1"))
    em2, ze15b, ze1b, m1sb, states = build(tracker=tr)
    poi2 = zone(caused_events=[bos()])
    s2 = em2.watch(poi2, ze15b, {Timeframe.M15: [poi2], Timeframe.H4: [], Timeframe.D1: []})
    m1b = [m1c(i, *r) for i, r in enumerate(M1_ROWS)]
    for i, c in enumerate(m1b):
        em2.step(MarketView(c.open_time + timedelta(minutes=1), m1b, i, [], m1sb, ze1b, states, [], {}, D(10000)))
    assert s2.state is State.WATCHING and not s2.history


def test_invalidated_poi_cancels_setup_permanently():
    em, ze15, ze1, m1s, states = build()
    poi = zone(caused_events=[bos()])
    setup = em.watch(poi, ze15, {})
    poi.invalidated_index = 3
    c = m1c(0, 30, 25)
    em.step(MarketView(c.open_time + timedelta(minutes=1), [c], 0, [], m1s, ze1, states, [], {}, D(10000)))
    assert setup.cancelled == "POI_INVALIDATED"


# ---------------- D-02 rafine M15 ----------------
def test_h4_poi_waits_for_refined_m15_zone_touch():
    em, ze15, ze1, m1s, states = build()
    h4 = zone(tf=Timeframe.H4, top=30, bottom=5, zid="h4", caused_events=[bos(tf=Timeframe.H4)])
    refined = zone(top=14, bottom=10, zid="r15", caused_events=[bos()])
    zones = {Timeframe.M15: [refined], Timeframe.H4: [h4], Timeframe.D1: []}
    setup = em.watch(h4, ze15, zones)
    rows = [(33, 31), (32, 28), (29, 25), (28, 22)]                      # H4'e girer ama rafine zona (≤14) değmez
    m1 = [m1c(i, *r) for i, r in enumerate(rows)]
    for i, c in enumerate(m1):
        m1s.update(c)
        em.step(MarketView(c.open_time + timedelta(minutes=1), m1[:i + 1], i, [], m1s, ze1, states, [], zones, D(10000)))
    assert setup.state is State.WATCHING and not setup.history
    rows2 = rows + [(20, 13)]                                            # rafine zona dokunuş
    m1 = [m1c(i, *r) for i, r in enumerate(rows2)]
    c = m1[-1]
    m1s.update(c)
    em.step(MarketView(c.open_time + timedelta(minutes=1), m1, 4, [], m1s, ze1, states, [], zones, D(10000)))
    assert setup.mitigated_zone is refined and setup.state is State.CONFIRMATION_PENDING


# ---------------- RISK girişi ve DOUBLE_CONFIRMATION ----------------
def test_double_confirmation_not_coded_q_e4():
    with pytest.raises(NotImplementedError, match="Q-E4"):
        EntryParams("DOUBLE_CONFIRMATION", False, True, True, "REJECT", "REJECT", 10, 2 * PIP, PIPETTE, D(0))


def test_risk_entry_places_limit_on_poi_without_ltf_confirmation():
    em, ze15, ze1, m1s, states = build(entry_type="RISK")
    poi = zone(caused_events=[bos()])
    rows = [(60, 55), (59, 54)]                                          # fiyat POI'nin çok üstünde, girişe değmedi
    s, out, _ = run_path(em, ze1, m1s, states, poi, ze15, rows=rows)
    sig = next(e for e in out if e.kind == "SIGNAL")
    assert sig.intent.entry_zone_kind == "POI" and sig.intent.stop == px("9.9") and sig.intent.entry == px("11.9")
    assert [h[2] for h in s.history][-1] is State.ORDER_PENDING


# ---------------- yardımcılar ----------------
def test_choose_entry_zone_picks_latest_flip_and_earliest_extreme():
    ze = ZoneEngine(Timeframe.M1, ZoneParams(PIP, "RANGE", 3, D(2), D(2)),
                    StructureEngine(Timeframe.M1, StructureParams.internal_only_params(PIP)))
    ch = make_choch()
    f1 = zone(tf=Timeframe.M1, origin=Origin.FLIP, is_flip=True, zid="f1", caused_events=[ch]); f1.created_index = 5
    f2 = zone(tf=Timeframe.M1, origin=Origin.FLIP, is_flip=True, zid="f2", caused_events=[ch]); f2.created_index = 8
    e1 = zone(tf=Timeframe.M1, zid="e1", caused_events=[ch]); e1.created_index = 3
    other = zone(tf=Timeframe.M1, zid="x", caused_events=[make_choch()])
    ze.zones += [f1, f2, e1, other]
    assert choose_entry_zone(ch, ze, False) == (f2, "FLIP")
    f2.is_sweep = f1.is_sweep = False
    assert choose_entry_zone(ch, ze, True) == (None, "NONE")             # flip sweep almadı; algılanan "extreme" zon artık kullanılmaz (Q-Z11)
    ze.zones[:] = [other]
    assert choose_entry_zone(ch, ze, False) == (None, "NONE")


def test_first_target_pro_vs_counter_and_short_mirror():
    st = {Timeframe.M15: state(Timeframe.M15, B, 0, 100)}
    assert first_target(Side.LONG, TrendClass.PRO, px(20), st, []) == px(100)
    sup = zone(kind=ZoneKind.SUPPLY, top=70, bottom=60, caused_events=[bos(d=S)])
    assert first_target(Side.LONG, TrendClass.COUNTER_HTF, px(20), st, [sup]) == px(60)            # sonraki M15 arz zonu daha yakın
    assert first_target(Side.LONG, TrendClass.PRO, px(20), st, [sup]) == px(100)                   # PRO'da zon dikkate alınmaz
    assert first_target(Side.LONG, TrendClass.PRO, px(120), st, []) is None
    st_b = {Timeframe.M15: state(Timeframe.M15, S, 0, 100)}
    assert first_target(Side.SHORT, TrendClass.PRO, px(80), st_b, []) == px(0)


def test_visit_start_is_first_candle_of_contiguous_inside_run():
    poi = zone()
    m1 = [m1c(i, *r) for i, r in enumerate(M1_ROWS)]
    assert visit_start(m1, poi, 7) == 7
    longer = m1[:8] + [m1c(8, 15, 11), m1c(9, 14, 9)]
    assert visit_start(longer, poi, 9) == 7


# ---------------- durum makinesi ----------------
def test_transition_table_matches_spec_and_illegal_moves_raise():
    s = Setup("x", "EURUSD", zone(), B)
    with pytest.raises(IllegalTransition):
        s.to(State.ORDER_PENDING, T0)                         # WATCHING → ORDER_PENDING yasak
    s.to(State.POI_MITIGATED, T0)
    with pytest.raises(IllegalTransition):
        s.to(State.POSITION_OPEN, T0)
    assert ALLOWED[State.POSITION_OPEN] == {State.RISK_FREE, State.CLOSED}
    assert ALLOWED[State.CLOSED] == {State.WATCHING, State.DAY_LOCKED} and ALLOWED[State.DAY_LOCKED] == {State.IDLE}
    for st in State:                                           # her durumun çıkışı tanımlı
        assert st in ALLOWED


def test_position_lifecycle_third_loss_locks_day_and_new_day_unlocks():
    em, ze15, ze1, m1s, states = build()
    ch = make_choch()
    with_zones(ze1, ch)
    s, out, _ = run_path(em, ze1, m1s, states, zone(caused_events=[bos()]), ze15, choch=ch)
    em.mark_filled(s, T0 + timedelta(minutes=20))
    assert s.state is State.POSITION_OPEN
    em.tracker.record_close(T0, D("-1")); em.tracker.record_close(T0, D("-1"))             # önceki iki kayıp
    assert em.mark_closed(s, T0 + timedelta(hours=1), D("-1")) is State.DAY_LOCKED and s.state is State.DAY_LOCKED
    assert [h[2] for h in s.history][-2:] == [State.CLOSED, State.DAY_LOCKED]
    em.new_day(T0 + timedelta(hours=1))
    assert s.state is State.DAY_LOCKED                                                      # aynı gün hâlâ kilitli
    em.new_day(T0 + timedelta(days=1))                                                      # İstanbul gece yarısı geçti
    assert s.state is State.WATCHING


def test_global_state_helper():
    assert global_state(True, True, 3) is State.DAY_LOCKED and global_state(False, False, 3) is State.IDLE
    assert global_state(True, False, 0) is State.MAPPING and global_state(True, False, 2) is State.WATCHING


def test_entry_params_from_config_requires_policies():
    p = EntryParams.from_config(CFG, "EURUSD")
    assert (p.duplicate_policy, p.opposite_policy, p.entry_type, p.v_shape_max_candles) == ("REJECT", "REJECT", "CONFIRMATION", 10)


# ---------------- Q-E8 (KULLANICI KARARI): izin reddinde POI_MITIGATED'da bekle ----------------
def run_wait(m15_from=None, m15_time_min=9, choch_idx=CHOCH_IDX, extra=None, states=PRO_COUNTER, rows=M1_ROWS, poi=None,
             double_bos_events=None):
    em, ze15, ze1, m1s, _ = build()
    ch = StructureEvent(Timeframe.M1, EventType.CHOCH, B, px(15), choch_idx, T0 + timedelta(minutes=choch_idx), False,
                        level_index=5, origin_index=7)
    with_zones(ze1, ch)
    poi = poi or zone(caused_events=[bos()])
    zones = {Timeframe.M15: [poi], Timeframe.H4: [], Timeframe.D1: []}
    setup = em.watch(poi, ze15, zones)
    m1 = [m1c(i, *r) for i, r in enumerate(rows)]
    m15ch = StructureEvent(Timeframe.M15, EventType.CHOCH, B, px(1), 3, T0 + timedelta(minutes=m15_time_min), False)
    out, states_seen = [], []
    for i, c in enumerate(m1):
        m1s.update(c)
        m15 = ([m15ch] if (m15_from is not None and i >= m15_from) else []) + list(double_bos_events or [])
        evs = [ch] if i == choch_idx else []
        out += em.step(MarketView(c.open_time + timedelta(minutes=1), m1, i, evs, m1s, ze1, states, m15, zones, D(10000)))
        states_seen.append(setup.state)
    return setup, out, states_seen


def test_q_e8_denied_setup_waits_in_poi_mitigated_without_signal():
    s, out, seen = run_wait(m15_from=None)
    assert seen[7:] == [State.POI_MITIGATED] * 4 and not [e for e in out if e.kind == "SIGNAL"]      # bekleme süresince limit sinyal yok
    assert s.wait_reason == "PERMISSION" and len(s.rejections) == 1                                    # neden tek kez kaydedilir
    assert ALLOWED[State.POI_MITIGATED] >= {State.WATCHING, State.CONFIRMATION_PENDING}


def test_q_e8_m15_choch_after_price_left_poi_resumes_m1_entry_search():
    # fiyat idx8'de POI'den çıktı; M15 CHoCH (07:09) idx9'da görünür; M1 CHoCH idx10 → sinyal
    s, out, seen = run_wait(m15_from=9, m15_time_min=9)
    assert seen[7:9] == [State.POI_MITIGATED, State.POI_MITIGATED] and seen[9] is State.CONFIRMATION_PENDING
    (sig,) = [e for e in out if e.kind == "SIGNAL"]
    assert sig.intent.entry_zone_kind == "FLIP" and s.state is State.ORDER_PENDING
    assert [h[2] for h in s.history] == [State.POI_MITIGATED, State.CONFIRMATION_PENDING, State.ENTRY_READY, State.ORDER_PENDING]


def test_q_e8_m1_choch_before_permission_opens_is_not_used_and_setup_keeps_waiting():
    s, out, seen = run_wait(m15_from=11, m15_time_min=11, rows=M1_ROWS + [(20, 17)])   # izin idx11'de açılır; M1 CHoCH idx10'da geçmişte kaldı
    assert not [e for e in out if e.kind == "SIGNAL"] and seen[10] is State.POI_MITIGATED and seen[-1] is State.CONFIRMATION_PENDING


def test_q_e8_waiting_setup_is_cancelled_when_poi_invalidated():
    em, ze15, ze1, m1s, _ = build()
    poi = zone(caused_events=[bos()])
    zones = {Timeframe.M15: [poi], Timeframe.H4: [], Timeframe.D1: []}
    s = em.watch(poi, ze15, zones)
    m1 = [m1c(i, *r) for i, r in enumerate(M1_ROWS)]
    for i, c in enumerate(m1[:9]):
        m1s.update(c)
        em.step(MarketView(c.open_time + timedelta(minutes=1), m1, i, [], m1s, ze1, PRO_COUNTER, [], zones, D(10000)))
    assert s.state is State.POI_MITIGATED
    poi.invalidated_index = 5
    em.step(MarketView(m1[9].open_time + timedelta(minutes=1), m1, 9, [], m1s, ze1, PRO_COUNTER, [], zones, D(10000)))
    assert s.cancelled == "POI_INVALIDATED" and s.state is State.WATCHING and s not in em.setups


def test_q_e8_counter_htf_double_bos_wait_then_proceeds():
    states = {Timeframe.H4: state(Timeframe.H4, S), Timeframe.M15: state(Timeframe.M15, B)}
    s, out, seen = run_wait(states=states, double_bos_events=[bos(minute=0)])
    assert seen[7] is State.POI_MITIGATED and s.wait_reason == "COUNTER_HTF_NEEDS_DOUBLE_BOS"
    s2, out2, seen2 = run_wait(states=states, double_bos_events=[bos(minute=0), bos(minute=15)])
    assert [e for e in out2 if e.kind == "SIGNAL"] and s2.state is State.ORDER_PENDING


# ---------------- Q-L3 sınır sayaçları ----------------
def test_q_l3_liquidation_window_cap_is_flagged(monkeypatch):
    import importlib
    L = importlib.import_module("photon.liquidity.liquidation")        # paket `liquidation` adını fonksiyonla gölgeler
    liq = L.liquidation
    m1 = [m1c(i, *r) for i, r in enumerate(M1_ROWS[:8])]
    poi = zone()
    ok = liq(m1, poi, 7, 2 * PIP, PIPETTE)
    assert ok.found and not ok.window_capped
    monkeypatch.setattr(L, "MAX_WINDOW", 2)
    capped = liq(m1, poi, 7, 2 * PIP, PIPETTE)
    assert capped.window_capped and not capped.found                       # sınır olmasa bulunurdu → "elenen durum"


def test_q_l3_zone_engine_limit_counters(monkeypatch):
    from photon.zones import detect as D_
    st = StructureEngine(Timeframe.M15, StructureParams(PIP, D(15), True, 2))
    ze = ZoneEngine(Timeframe.M15, ZoneParams(PIP, "RANGE", 3, D(2), D(2), retire_after=2), st)
    z = zone(tf=Timeframe.M15, caused_events=[bos()])
    z.created_index = 0
    ze.zones.append(z); ze._act.append(z)
    st.start_auto()
    for i in range(5):
        c = Candle("EURUSD", Timeframe.M15, T0 + timedelta(minutes=15 * i), px(12), px(13), px(11), px(12), True)
        ze.update(c, st.update(c))
    assert ze.limits["retired"] == 1 and ze.limits["retired_valid"] == 1
    monkeypatch.setattr(D_, "MAX_CHAIN_LOOKBACK", 3)
    rows = [(50, 0, 25)] + [(30 - i * 0.1, 20 + i * 0.1, 25) for i in range(6)] + [(60, 40, 58)]    # zincir lookback'ten uzun
    cs = [Candle("EURUSD", Timeframe.M15, T0 + timedelta(minutes=15 * i), px(r[2]), px(r[0]), px(r[1]), px(r[2]), True) for i, r in enumerate(rows)]
    stats = {"range_lookback_exhausted": 0}
    D_.range_zone(cs, len(cs) - 1, PIPETTE, 3, stats)
    assert stats["range_lookback_exhausted"] == 1            # en dıştaki bulunan mother tam sınırda: daha eski mother olabilirdi
    monkeypatch.setattr(D_, "MAX_CHAIN_LOOKBACK", 10)
    rows2 = [(50, 0, 25)] + [(30, 20, 25)] * 2 + [(60, 40, 58)]
    cs2 = [Candle("EURUSD", Timeframe.M15, T0 + timedelta(minutes=15 * i), px(r[2]), px(r[0]), px(r[1]), px(r[2]), True) for i, r in enumerate(rows2)]
    stats2 = {"range_lookback_exhausted": 0}
    assert D_.range_zone(cs2, len(cs2) - 1, PIPETTE, 3, stats2) is not None and stats2["range_lookback_exhausted"] == 0
