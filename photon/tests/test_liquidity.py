"""LQ-R001 (eşit tepe/dip ≤2 pip), LQ-R002 sweep zone, LQ-R003 inducement, liquidation (EN-R001/1), V-shape önerisi."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.data import Candle, Timeframe
from photon.liquidity import (Side, Source, equal_pools, has_inducement, is_sweep_zone, liquidation, minor_highs,
                              minor_lows, swept, v_shape_exit)
from photon.structure.models import Kind, Strength, SwingPoint
from photon.zones.models import Origin, Zone, ZoneKind

UTC = timezone.utc
T0 = datetime(2021, 9, 1, tzinfo=UTC)
BASE, PIP, PIPETTE = D("1.1000"), D("0.0001"), D("0.00001")
TOL = 2 * PIP


def px(p) -> D:
    return BASE + D(str(p)) * PIP


def cd(i, h, l, c=None, o=None, tf=Timeframe.M1) -> Candle:
    h, l = D(str(h)), D(str(l))
    c = (h + l) / 2 if c is None else D(str(c))
    o = c if o is None else D(str(o))
    return Candle("EURUSD", tf, T0 + timedelta(minutes=i), px(o), px(max(h, o, c)), px(min(l, o, c)), px(c), True)


def hl(rows, tf=Timeframe.M1):
    return [cd(i, h, l, tf=tf) for i, (h, l) in enumerate(rows)]


# ---------------- minor + eşit tepe/dip ----------------
def test_minor_extremes_ms_r002_style():
    c = hl([(10, 5), (12, 6), (11, 5.5), (13, 7), (13, 8)])
    assert minor_highs(c, PIPETTE) == [1, 3]            # 3. mum: 13 > 11 ve sonraki 13 onu kıramadı
    c2 = hl([(10, 5), (12, 6), (11, 5.5), (13, 7), (12.5, 8), (12, 9)])
    assert minor_highs(c2, PIPETTE) == [1, 3]
    assert minor_lows(hl([(10, 8), (9, 6), (9.5, 7), (9, 5), (9.2, 5.5), (9, 6)]), PIPETTE) == [1, 3]


@pytest.mark.parametrize("second,eq", [("12.0", True), ("11.9", True), ("12.1", False), ("12.2", False), ("10.0", True), ("8.0", True), ("7.9", False)])
def test_equal_highs_tolerance_boundary_inclusive_2_pip(second, eq):
    # ilk tepe 10; ikincisi 10±: |fark| ≤ 2 pip → eşit (SINIR DAHİL)
    rows = [(5, 0), (10, 4), (7, 3), (float(second), 4), (7, 3), (6, 2)]
    c = hl(rows)
    idx = minor_highs(c, PIPETTE)
    pools = equal_pools(c, idx, Side.HIGH, TOL)
    assert bool(pools) is eq


def test_equal_pool_broken_when_price_exceeds_between():
    rows = [(5, 0), (10, 4), (7, 3), (20, 5), (7, 3), (10, 4), (7, 3), (6, 2)]     # arada 20'ye çıkıldı
    c = hl(rows)
    idx = minor_highs(c, PIPETTE)
    pools = equal_pools(c, idx, Side.HIGH, TOL)
    assert all(p.index != 5 for p in pools if p.price == px(10))


def test_equal_lows_and_pool_level_is_the_outer_extreme():
    rows = [(10, 8), (9, 5), (9.5, 6), (9, 4.0), (9.5, 6), (9, 5), (9.5, 6)]
    c = hl(rows)
    idx = minor_lows(c, PIPETTE)
    pools = equal_pools(c, idx, Side.LOW, TOL)
    p = pools[0]
    assert p.side is Side.LOW and p.source is Source.EQ and p.price == px(4) and p.index == 3   # en düşük dip = süpürme eşiği


def test_swept_needs_one_pipette_beyond():
    from photon.liquidity import Level
    lv = Level(Side.HIGH, px(10), 0, Source.MINOR)
    assert not swept(lv, cd(1, 10, 5), PIPETTE) and swept(lv, cd(1, "10.1", 5), PIPETTE)


# ---------------- sweep zone (LQ-R002) ----------------
def swing(kind, price, idx):
    return SwingPoint(Timeframe.M15, px(price), idx, kind, Strength.STRONG, True)


def test_demand_zone_that_swept_prior_low_and_closed_back_is_sweep_zone():
    # swing low 0 (idx0); sonra yükseliş; talep oluşurken (idx 4-5) dibin altına wick (-1) ve geri kapanış
    c = [cd(0, 3, 0, 2), cd(1, 10, 4, 9), cd(2, 12, 8, 11), cd(3, 11, 6, 7),
         cd(4, 7, -1, 0, o=6), cd(5, 14, 1, 13, o=0)]                    # idx4 bearish wick -1 < 0; kopuş idx5 kapanış 13 > 0
    z = Zone("z", Timeframe.M15, ZoneKind.DEMAND, Origin.PIVOT, "RANGE", px(7), px(-1), 4, 5, T0)
    log = [swing(Kind.LOW, 0, 0), swing(Kind.HIGH, 12, 2)]
    assert is_sweep_zone(z, c, log, TOL, PIPETTE)
    # wick seviyeyi geçmediyse sweep değil
    c2 = [cd(0, 3, 0, 2), cd(1, 10, 4, 9), cd(2, 12, 8, 11), cd(3, 11, 6, 7), cd(4, 7, 0.5, 1, o=6), cd(5, 14, 1, 13, o=1)]
    z2 = Zone("z", Timeframe.M15, ZoneKind.DEMAND, Origin.PIVOT, "RANGE", px(7), px("0.5"), 4, 5, T0)
    assert not is_sweep_zone(z2, c2, log, TOL, PIPETTE)


def test_already_swept_level_does_not_count_and_supply_mirror():
    c = [cd(0, 3, 0, 2), cd(1, 10, -2, 1), cd(2, 12, 8, 11), cd(3, 11, 6, 7), cd(4, 7, -1, 0, o=6), cd(5, 14, 1, 13, o=0)]
    z = Zone("z", Timeframe.M15, ZoneKind.DEMAND, Origin.PIVOT, "RANGE", px(7), px(-1), 4, 5, T0)
    assert not is_sweep_zone(z, c, [swing(Kind.LOW, 0, 0)], TOL, PIPETTE)          # idx1'de zaten -2'ye inildi
    cs = [cd(0, 10, 7, 8), cd(1, 6, 0, 5), cd(2, 4, -2, 0), cd(3, 6, 2, 5), cd(4, 12, 4, 11, o=5), cd(5, 8, -6, -5, o=11)]
    zs = Zone("s", Timeframe.M15, ZoneKind.SUPPLY, Origin.PIVOT, "RANGE", px(12), px(4), 4, 5, T0)
    assert is_sweep_zone(zs, cs, [swing(Kind.HIGH, 10, 0), swing(Kind.LOW, -2, 2)], TOL, PIPETTE)


# ---------------- inducement (LQ-R003) ----------------
def test_inducement_unswept_minor_low_above_demand_zone():
    # talep [0..4] idx1; fiyat yükseldi ve geri dönerken idx4'te minor dip 12 (zonun 8 pip üstü), süpürülmedi
    c = hl([(3, 0), (4, 2), (20, 10), (22, 16), (18, 12), (19, 14), (17, 15)])
    z = Zone("z", Timeframe.M15, ZoneKind.DEMAND, Origin.PIVOT, "RANGE", px(4), px(0), 0, 1, T0)
    assert has_inducement(z, c, len(c), TOL, PIPETTE)
    # sonradan süpürülmüşse (low 11'e inildi) artık inducement yok
    c2 = c + [cd(7, 16, 11, 12)]
    assert not has_inducement(z, c2, len(c2), TOL, PIPETTE)


def test_inducement_level_must_be_in_front_of_zone_not_inside_or_behind():
    c = hl([(3, 0), (4, 2), (20, 3.5), (22, 3.8), (18, 3.6), (19, 3.9), (17, 3.8)])      # minor dipler zonun içinde (≤4)
    z = Zone("z", Timeframe.M15, ZoneKind.DEMAND, Origin.PIVOT, "RANGE", px(4), px(0), 0, 1, T0)
    assert not has_inducement(z, c, len(c), TOL, PIPETTE)


# ---------------- liquidation (EN-R001 adım 1; Q-L1 kararı c: EQ veya M1 iç referans) ----------------
def poi_demand():
    return Zone("z", Timeframe.M15, ZoneKind.DEMAND, Origin.PIVOT, "RANGE", px(10), px(5), 0, 1, T0)


def test_liquidation_equal_lows_swept_on_the_way_into_demand():
    # eşit dipler 12 / 12.1 (≤2 pip) oluşur, sonra wick 11.5 süpürür, sonra zona 9'a dokunur
    rows = [(20, 15), (18, 13), (16, 12), (17, 13), (16, 12.1), (17, 13), (15, 11.5), (13, 9)]
    c = hl(rows)
    r = liquidation(c, poi_demand(), len(c) - 1, TOL, PIPETTE)
    assert r.found and r.level.source is Source.EQ and r.level.price == px(12) and r.sweep_index == 6 and r.touch_index == 7


def test_ordinary_minor_low_alone_does_not_count_q_l1():
    rows = [(20, 15), (18, 13), (16, 12), (17, 13), (15, 11.5), (13, 9)]       # tek minor dip (12): eşit değil, iç referans verilmedi
    c = hl(rows)
    r = liquidation(c, poi_demand(), len(c) - 1, TOL, PIPETTE)
    assert not r.found and r.reason == "NO_SWEEP"


def test_internal_reference_level_swept_counts():
    from photon.liquidity import Level
    rows = [(20, 15), (18, 13), (16, 12), (17, 13), (15, 11.5), (13, 9)]
    c = hl(rows)
    ref = Level(Side.LOW, px(12), 2, Source.INTERNAL)                         # M1 iç yapının geçerli referans dibi
    r = liquidation(c, poi_demand(), len(c) - 1, TOL, PIPETTE, [ref])
    assert r.found and r.level.source is Source.INTERNAL and r.sweep_index == 4 and r.touch_index == 5
    # yanlış taraf (high-tipi), zon içindeki veya pencere öncesi referans sayılmaz
    assert not liquidation(c, poi_demand(), len(c) - 1, TOL, PIPETTE, [Level(Side.HIGH, px(12), 2, Source.INTERNAL)]).found
    assert not liquidation(c, poi_demand(), len(c) - 1, TOL, PIPETTE, [Level(Side.LOW, px(9.5), 2, Source.INTERNAL)]).found
    assert not liquidation(c, poi_demand(), len(c) - 1, TOL, PIPETTE, [Level(Side.LOW, px(12), 5, Source.INTERNAL)]).found   # touch'tan sonra


def test_internal_levels_from_real_m1_internal_engine():
    from photon.liquidity import internal_levels
    from photon.structure import StructureEngine, StructureParams
    e = StructureEngine(Timeframe.M1, StructureParams.internal_only_params(PIP))
    for cnd in hl([(10, 5), (12, 6), (11, 6.5), (13, 7)]):
        e.update(cnd)
    (lv,) = internal_levels(e)
    assert lv.side is Side.LOW and lv.source is Source.INTERNAL and lv.price == px(6.5) and lv.index == 2


def test_liquidation_not_mitigated_and_no_sweep_cases():
    c = hl([(20, 15), (18, 14), (17, 13)])
    assert liquidation(c, poi_demand(), len(c) - 1, TOL, PIPETTE).reason == "NOT_MITIGATED"
    c = hl([(20, 15), (13, 9)])                                                # tek hamle: süpürülecek seviye yok
    r = liquidation(c, poi_demand(), 1, TOL, PIPETTE)
    assert not r.found and r.reason == "NO_SWEEP" and r.touch_index == 1


def test_liquidation_level_must_be_outside_zone_and_window_starts_after_previous_visit():
    # önceki ziyaret idx2 (low 9 zonda); idx0-1'deki eşit dipler pencere dışı; yeni iniş eşit dipleri idx4/idx6
    rows = [(20, 12), (18, 12.1), (15, 9), (16, 13), (15, 12), (16, 13), (14, 12.1), (15, 13), (14, 11.5), (13, 9)]
    c = hl(rows)
    r = liquidation(c, poi_demand(), 9, TOL, PIPETTE)
    assert r.found and r.window_start == 3 and r.level.source is Source.EQ and r.level.index == 6 and r.touch_index == 9
    c = hl([(20, 15), (14, 9.5), (13, 9.0), (14, 9.2)])                        # zon içinde oluşan uçlar seviye değil
    assert not liquidation(c, poi_demand(), 3, TOL, PIPETTE).found


def test_liquidation_supply_mirror_with_equal_highs():
    z = Zone("s", Timeframe.M15, ZoneKind.SUPPLY, Origin.PIVOT, "RANGE", px(20), px(15), 0, 1, T0)
    rows = [(8, 3), (10, 4), (12, 8), (11, 6), (12.1, 9), (11, 7), (12, 8), (14.5, 10), (16, 12)]
    c = hl(rows)
    r = liquidation(c, z, len(c) - 1, TOL, PIPETTE)
    assert r.found and r.level.side is Side.HIGH and r.level.source is Source.EQ and r.touch_index == 8


def test_v_shape_exit_candles_to_choch():
    assert v_shape_exit(10, 15, 5) and not v_shape_exit(10, 16, 5) and v_shape_exit(10, 10, 0)
    with pytest.raises(ValueError):
        v_shape_exit(10, 9, 5)
