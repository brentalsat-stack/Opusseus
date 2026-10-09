"""SD-R001..R007, T-SD-01..03. Fiyatlar 1.1000 tabanına göre PIP cinsinden."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.data import Candle, Timeframe
from photon.structure import EventType, Seed, StructureEngine, StructureParams, Trend
from photon.zones.detect import pivot_zone, range_zone
from photon.zones.engine import ZoneEngine, ZoneParams
from photon.zones.models import Context, Origin, ZoneKind

UTC = timezone.utc
T0 = datetime(2021, 9, 1, tzinfo=UTC)
BASE, PIP, PIPETTE = D("1.1000"), D("0.0001"), D("0.00001")


def px(p) -> D:
    return BASE + D(str(p)) * PIP


def cd(i, o, h, l, c, tf=Timeframe.M15) -> Candle:
    return Candle("EURUSD", tf, T0 + timedelta(minutes=15 * i), px(o), px(h), px(l), px(c), True)


def series(rows, tf=Timeframe.M15):
    return [cd(i, *r, tf=tf) for i, r in enumerate(rows)]


# ---------------- pivot (SD-R002) ----------------
def test_pivot_demand_stb_whole_run_and_single_candle_modes():
    # iki bearish mum (STB) + bullish kopuş mumu onları yutuyor
    cs = series([(10, 12, 9, 11), (11, 11, 6, 7), (7, 8, 3, 4), (4, 14, 4, 13)])
    g = pivot_zone(cs, 3, PIPETTE, "RANGE")
    assert (g.kind, g.origin, g.draw) == (ZoneKind.DEMAND, Origin.PIVOT, "RANGE")
    assert g.top == px(11) and g.bottom == px(3) and g.first_index == 1       # iki bearish mumun wick'li kutusu (idx0 bullish → dışarıda)
    g1 = pivot_zone(cs, 3, PIPETTE, "CANDLE")
    assert g1.draw == "CANDLE" and (g1.top, g1.bottom, g1.first_index) == (px(8), px(3), 2)       # son sell-to-buy mumu


def test_pivot_requires_engulf_by_close_by_a_pipette():
    cs = series([(10, 12, 9, 11), (11, 11, 6, 7), (7, 8, 3, 4), (4, 14, 4, 8)])      # kapanış 8 == koşunun high'ı (11 değil)
    # run: idx2 (high 8) → kopuş close 8 → 8-8=0 < pipette → yutmuyor
    assert pivot_zone(cs, 3, PIPETTE, "RANGE") is None
    cs2 = series([(10, 12, 9, 11), (11, 11, 6, 7), (7, 8, 3, 4), (4, 14, 4, "8.1")])
    g = pivot_zone(cs2, 3, PIPETTE, "RANGE")
    assert g is not None and g.first_index == 2                                       # idx1'in high'ı 11 > 8.1 → koşu yalnız idx2


def test_pivot_supply_btS_mirror():
    cs = series([(10, 12, 9, 11), (11, 13, 11, 12), (12, 15, 12, 14), (14, 14, 2, 3)])
    g = pivot_zone(cs, 3, PIPETTE, "RANGE")
    assert g.kind is ZoneKind.SUPPLY and (g.top, g.bottom, g.first_index) == (px(15), px(9), 0)


def test_pivot_none_when_previous_candle_not_counter_direction():
    cs = series([(10, 12, 9, 11), (11, 13, 10, 12), (12, 20, 12, 19)])    # bullish arkası bullish
    assert pivot_zone(cs, 2, PIPETTE, "RANGE") is None


def test_unknown_draw_mode_not_coded():
    with pytest.raises(NotImplementedError):
        pivot_zone(series([(1, 2, 0, 1)] * 3), 2, PIPETTE, "FRACTAL_WICK")


# ---------------- range (SD-R001, kullanıcı tanımı) ----------------
def test_range_needs_three_candle_chain_and_close_breakout():
    # mother + 2 inside + yukarı kapanışlı kopuş
    cs = series([(10, 20, 0, 10), (10, 15, 5, 12), (12, 18, 4, 8), (8, 30, 8, 28)])
    g = range_zone(cs, 3, PIPETTE, 3)
    assert (g.kind, g.origin, g.top, g.bottom, g.first_index) == (ZoneKind.DEMAND, Origin.RANGE, px(20), px(0), 0)
    # yalnız 1 inside → zincir 2 mum → zon yok
    assert range_zone(series([(10, 20, 0, 10), (10, 15, 5, 12), (8, 30, 8, 28)]), 2, PIPETTE, 3) is None


def test_range_wick_only_exit_is_not_breakout_and_down_is_supply():
    cs = series([(10, 20, 0, 10), (10, 15, 5, 12), (12, 18, 4, 8), (8, 25, 8, 19)])     # kapanış 19 < 20 → kopuş yok
    assert range_zone(cs, 3, PIPETTE, 3) is None
    cs = series([(10, 20, 0, 10), (10, 15, 5, 12), (12, 18, 4, 8), (8, 9, -10, -5)])
    g = range_zone(cs, 3, PIPETTE, 3)
    assert g.kind is ZoneKind.SUPPLY and g.top == px(20) and g.bottom == px(0)


def test_range_close_equal_to_edge_is_not_breakout():
    cs = series([(10, 20, 0, 10), (10, 15, 5, 12), (12, 18, 4, 8), (8, 30, 8, 20)])      # kapanış == high
    assert range_zone(cs, 3, PIPETTE, 3) is None
    cs = series([(10, 20, 0, 10), (10, 15, 5, 12), (12, 18, 4, 8), (8, 30, 8, "20.1")])
    assert range_zone(cs, 3, PIPETTE, 3) is not None


def test_range_prefers_outermost_mother_that_breaks():
    # m0 geniş; m1 m0'ın içinde; zincirler iç içe: kopuş m1 aralığının dışında ama m0'ın içinde → m1 seçilir
    cs = series([(10, 40, -20, 10), (10, 20, 0, 10), (10, 15, 5, 12), (12, 18, 4, 8), (8, 30, 8, 25)])
    g = range_zone(cs, 4, PIPETTE, 3)
    assert g.first_index == 1 and g.top == px(20)
    # kopuş m0 aralığının da dışında → en dıştaki m0
    cs = series([(10, 40, -20, 10), (10, 20, 0, 10), (10, 15, 5, 12), (12, 18, 4, 8), (8, 60, 8, 55)])
    assert range_zone(cs, 4, PIPETTE, 3).first_index == 0


# ---------------- motor: tür, bağlama, geçerlilik, mitigation, flip ----------------
def params(**kw):
    base = dict(pip_size=PIP, draw_mode="RANGE", min_chain=3, reaction_min_pips=D(2), eqh_tol_pips=D(2))
    return ZoneParams(**{**base, **kw})


def run(rows, seed_rows=None, zp=None, min_pips=1000):
    """Yapı + zon motorunu birlikte sür. seed_rows ile başlayan BULL yapı (strong low idx0, run idx1)."""
    cs = series(rows)
    sp = StructureParams(PIP, D(str(min_pips)), True, 2)
    st = StructureEngine(Timeframe.M15, sp)
    st.start(cs[:2], Seed(Trend.BULL, 1, 0, False, Trend.BULL, 0))
    ze = ZoneEngine(Timeframe.M15, zp or params(), st)
    for c in cs[:2]:
        ze.candles.append(c)
    for c in cs[2:]:
        ev = st.update(c)
        ze.update(c, ev)
    return ze, st


def test_zone_type_and_context_from_prior_swing_trend():
    rows = [(0, 5, -5, 2), (2, 12, 1, 10),                       # seed: BULL
            (10, 12, 8, 9), (9, 9, 5, 6), (6, 25, 6, 24)]        # bearish ×2 → bullish kopuş (talep, trend BULL → continuation)
    ze, _ = run(rows)
    (z,) = [z for z in ze.zones if z.origin is Origin.PIVOT]
    assert z.kind is ZoneKind.DEMAND and z.context is Context.CONTINUATION and z.created_index == 4 and not z.valid


def test_t_sd_01_zone_without_structure_break_is_invalid():
    rows = [(0, 5, -5, 2), (2, 12, 1, 10),
            (10, 12, 8, 9), (9, 9, 5, 6), (6, 25, 6, 24),
            (24, 26, 20, 22), (22, 24, 18, 20)]
    ze, st = run(rows, min_pips=1000)
    assert ze.zones and all(not z.valid for z in ze.zones)        # swing eşiği devasa → BOS yok; internal CHoCH yok
    assert not [e for e in st.events if e.type in (EventType.BOS, EventType.CHOCH)]


def test_structural_zone_linked_to_the_event_it_started():
    # idx0-1 seed; talep pivotu idx2-4; sonra internal high kırılımı yok; swing BOS (kapanış) ile yapı kırılır
    rows = [(0, 5, 0, 2), (30, 40, 29, 38),                        # swing high idx1=40 (onaylı olacak)
            (38, 39, 30, 31), (31, 32, 20, 21),                  # geri çekilme (pullback ≥ eşik → onay)
            (21, 22, 12, 13), (13, 14, 8, 9),                    # bearish koşu → STB talebi
            (9, 20, 9, 19), (19, 30, 18, 29), (29, 45, 28, 44)]  # yukarı: idx8 kapanış 44 > 40 → BOS
    ze, st = run(rows, min_pips=10)
    bos = [e for e in st.events if e.type is EventType.BOS]
    assert len(bos) == 1 and bos[0].origin_index == 5            # kutu min = idx5 (low 8)
    caused = [z for z in ze.zones if z.caused_events]
    assert len(caused) == 1
    z = caused[0]
    assert z.kind is ZoneKind.DEMAND and z.valid and z.caused_swing_bos and z.caused_event is bos[0]
    assert bos[0].origin_index <= z.created_index <= bos[0].break_index


def test_zone_needs_to_be_born_inside_the_window_of_the_break():
    rows = [(0, 5, 0, 2), (30, 40, 29, 38),
            (38, 39, 30, 31), (31, 32, 20, 21), (21, 22, 12, 13), (13, 14, 8, 9),
            (9, 20, 9, 19), (19, 30, 18, 29), (29, 45, 28, 44)]
    ze, _ = run(rows, min_pips=10)
    # pencere dışında (kutu minimumundan önce doğan) talep zonu bağlanmaz: tüm bağlı zonlar created_index ≥ 5
    assert all(z.created_index >= 5 for z in ze.zones if z.caused_events)


def test_mitigation_touch_and_invalidation_by_close():
    rows = [(0, 5, 0, 2), (2, 12, 1, 10),
            (10, 12, 8, 9), (9, 9, 5, 6), (6, 25, 6, 24),            # talep [5..12]
            (24, 26, 20, 22), (22, 23, 11, 12),                       # high ≥ bottom ve low 11 ≤ top 12 → dokunuş (idx6)
            (12, 13, 2, 3)]                                           # kapanış 3 < bottom 5 → geçersiz
    ze, _ = run(rows)
    z = next(z for z in ze.zones if z.origin is Origin.PIVOT)
    assert (z.top, z.bottom) == (px(12), px(5))
    assert z.mitigated_index == 6 and z.invalidated_index == 7 and not z.usable


def test_flip_failed_reaction_creates_opposite_zone_and_needs_valid_zone():
    # geçerli talep (BOS'a neden olmuş): sonra zona giriş, ≥2 pip tepki (hedefi kırmadan), tepki başlangıcının altına geçiş
    rows = [(0, 5, 0, 2), (30, 40, 29, 38),
            (38, 39, 30, 31), (31, 32, 20, 21), (21, 22, 12, 13), (13, 14, 8, 9),
            (9, 20, 9, 19), (19, 30, 18, 29), (29, 45, 28, 44),     # BOS; talep [8..14]; hedef (tepe) 45
            (44, 44, 13, 14),                                        # zona dokunuş (low 13 ≤ top 14): tepki başlangıcı rs=13
            (14, 18, 12.5, 17),                                      # tepki: rs=12.5 → yeni dip değil mi? 12.5<13 → rs=12.5, tepki sıfırlanır
            (17, 22, 14, 21),                                        # tepki ucu 22 → 22-12.5 ≥ 2
            (21, 21, 12, 12.5)]                                      # low 12 < rs 12.5 → FR → flip
    ze, st = run(rows, min_pips=10)
    zone = next(z for z in ze.zones if z.caused_events and z.kind is ZoneKind.DEMAND)
    flips = [z for z in ze.zones if z.is_flip]
    assert len(flips) == 1
    f = flips[0]
    assert f.kind is ZoneKind.SUPPLY and f.origin is Origin.FLIP and f.flipped_from == zone.id and f.context is Context.REVERSAL
    assert (f.bottom, f.top) == (px("12.5"), px(22)) and f.valid and zone.flipped_index == f.created_index and not zone.usable


@pytest.mark.parametrize("peak,flip", [("13.9", False), ("14.0", True)])
def test_flip_requires_reaction_of_at_least_2_pips(peak, flip):
    rows = [(0, 5, 0, 2), (30, 40, 29, 38),
            (38, 39, 30, 31), (31, 32, 20, 21), (21, 22, 12, 13), (13, 14, 8, 9),
            (9, 20, 9, 19), (19, 30, 18, 29), (29, 45, 28, 44),
            (44, 44, 12, 13),                                        # dokunuş; rs = 12
            (13, peak, 12.5, 13),                                    # tepki ucu: peak − 12 = 1.9 | 2.0 pip
            (13, 13, 11.8, 12)]                                      # rs'nin 2 pipette altı değil, 0.2 pip altı → FR (≥1 pipette)
    ze, _ = run(rows, min_pips=10)
    assert bool([z for z in ze.zones if z.is_flip]) is flip


def test_t_sd_02_straight_pass_without_reaction_is_not_flip():
    rows = [(0, 5, 0, 2), (30, 40, 29, 38),
            (38, 39, 30, 31), (31, 32, 20, 21), (21, 22, 12, 13), (13, 14, 8, 9),
            (9, 20, 9, 19), (19, 30, 18, 29), (29, 45, 28, 44),
            (44, 44, 13, 13.5),          # dokunuş
            (13.5, 13.6, 11, 11.5),      # tepkisiz derinleşme (tepki yok)
            (11.5, 11.6, 9, 9.5)]
    ze, _ = run(rows, min_pips=10)
    assert not [z for z in ze.zones if z.is_flip]


def test_reaction_that_breaks_target_means_zone_fulfilled_no_flip():
    rows = [(0, 5, 0, 2), (30, 40, 29, 38),
            (38, 39, 30, 31), (31, 32, 20, 21), (21, 22, 12, 13), (13, 14, 8, 9),
            (9, 20, 9, 19), (19, 30, 18, 29), (29, 45, 28, 44),
            (44, 44, 13, 14),
            (14, 50, 13.5, 49),          # hedefi (45) kırdı → fulfilled
            (49, 49, 5, 6)]              # sonradan aşağı geçiş artık flip değil
    ze, _ = run(rows, min_pips=10)
    z = next(z for z in ze.zones if z.caused_events and z.kind is ZoneKind.DEMAND)
    assert z.fulfilled_index is not None and not [x for x in ze.zones if x.is_flip]


def test_t_sd_03_flip_plus_choch_gives_flip_zone_with_structure_break():
    # flip sonrası aşağı yönlü kırılım flip zonuna bağlanır (SD-R007: flip + CHoCH/BOS)
    rows = [(0, 5, 0, 2), (30, 40, 29, 38),
            (38, 39, 30, 31), (31, 32, 20, 21), (21, 22, 12, 13), (13, 14, 8, 9),
            (9, 20, 9, 19), (19, 30, 18, 29), (29, 45, 28, 44),
            (44, 44, 13, 14), (14, 18, 12.5, 17), (17, 22, 14, 21), (21, 21, 12, 12.5),
            (12.5, 12.6, 5, 6), (6, 7, 0.5, 1)]                     # sert düşüş: internal low kırılır → CHoCH
    ze, st = run(rows, min_pips=10)
    f = next(z for z in ze.zones if z.is_flip)
    chochs = [e for e in st.events if e.type in (EventType.CHOCH, EventType.BOS) and e.dir is Trend.BEAR]
    assert chochs and f.valid and f.caused_events and f.caused_events[0] in chochs


def test_zone_params_from_config_and_d1_undefined():
    from photon.config import load_config
    cfg = load_config()
    p = ZoneParams.from_config(cfg, "EURUSD", Timeframe.M15)
    assert (p.draw_mode, p.min_chain, p.reaction_min_pips, p.eqh_tol_pips) == ("CANDLE", 3, D(2), D(2))
    assert ZoneParams.from_config(cfg, "EURUSD", Timeframe.H4).draw_mode == "RANGE"
    with pytest.raises(ValueError, match="Q-Z3"):
        ZoneParams.from_config(cfg, "EURUSD", Timeframe.D1)


def test_engine_rejects_open_candles_and_wrong_tf():
    ze, st = run([(0, 5, 0, 2), (2, 12, 1, 10), (10, 12, 8, 9)])
    bad = Candle("EURUSD", Timeframe.M15, T0 + timedelta(hours=9), px(1), px(2), px(0), px(1), False)
    with pytest.raises(ValueError):
        ze.update(bad, [])
    with pytest.raises(ValueError):
        ze.update(cd(20, 1, 2, 0, 1, tf=Timeframe.H4), [])


def test_sweep_flag_is_lazy_cached_and_uses_structure_swing_log():
    rows = [(0, 5, 0, 2), (30, 40, 29, 38),
            (38, 39, 30, 31), (31, 32, 20, 21), (21, 22, 12, 13), (13, 14, 8, 9),
            (9, 20, 9, 19), (19, 30, 18, 29), (29, 45, 28, 44)]
    ze, st = run(rows, min_pips=10)
    z = next(z for z in ze.zones if z.valid)
    assert z.is_sweep is None                                 # oluşurken hesaplanmadı (performans)
    v = ze.sweep_flag(z)
    assert z.is_sweep is v and ze.sweep_flag(z) is v
