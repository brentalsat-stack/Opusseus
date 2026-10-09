"""MS-R001..R009, R014 + FINAL_SPEC §25 T-MS-01..08. Fiyatlar 1.1000 tabanına göre PIP cinsinden yazılır."""
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.config import ConfigError, load_config
from photon.data import Candle, Timeframe
from photon.structure import (EventType, Kind, Seed, Strength, StructureEngine, StructureParams, Trend)

UTC = timezone.utc
T0 = datetime(2021, 9, 1, tzinfo=UTC)
BASE = D("1.1000")
PIP = D("0.0001")


def px(pips) -> D:
    return BASE + D(str(pips)) * PIP


def bar(i, h, l, c=None, tf=Timeframe.H4, complete=True) -> Candle:
    h, l = D(str(h)), D(str(l))
    c = (h + l) / 2 if c is None else D(str(c))
    return Candle("EURUSD", tf, T0 + timedelta(hours=4 * i), px(c), px(h), px(l), px(c), complete)


def bars(rows, start=0, tf=Timeframe.H4):
    return [bar(start + k, *r, tf=tf) for k, r in enumerate(rows)]


def params(min_pips=10, inclusive=True, min_candles=2):
    return StructureParams(PIP, D(str(min_pips)), inclusive, min_candles)


def engine(history, seed, **kw):
    e = StructureEngine(Timeframe.H4, params(**kw))
    e.start(history, seed)
    return e


def types(evs, *t):
    return [x for x in evs if x.type in t]


# --- ortak yükseliş senaryosu: strong low idx0 (0 pip), onaylı swing high idx2 (40 pip), geri çekilme ---
UP = [(5, 0), (20, 10), (40, 25), (35, 20), (30, 12), (33, 15)]
UP_SEED = Seed(Trend.BULL, swing_high_index=2, swing_low_index=0, swing_high_confirmed=True,
               internal_trend=Trend.BULL, internal_ref_index=0)


def up_engine(**kw):
    return engine(bars(UP), UP_SEED, **kw)


def test_t_ms_05_bos_by_close_and_box_rule():
    e = up_engine()
    evs = e.update(bar(6, 45, 30, c=42))
    (bos,) = types(evs, EventType.BOS)
    assert bos.dir is Trend.BULL and bos.level == px(40) and bos.by_close and bos.rule == "MS-R006/R007"
    st = e.state()
    assert st.swing_low.price == px(12) and st.swing_low.index == 4 and st.swing_low.strength is Strength.STRONG  # box min [2..6]
    assert st.swing_high.price == px(45) and not st.swing_high.confirmed and st.swing_high.strength is Strength.WEAK
    assert st.eq is None


def test_t_ms_04_wick_above_close_inside_is_not_bos():
    e = up_engine()
    assert types(e.update(bar(6, 45, 30, c=39)), EventType.BOS) == []     # sweep
    assert e.state().swing_high.price == px(40) and e.state().swing_high.confirmed
    assert len(types(e.update(bar(7, 44, 35, c=41)), EventType.BOS)) == 1  # sonraki kapanış → BOS (level 40)


def test_ms_r001_equality_is_not_a_break():
    e = up_engine()
    assert types(e.update(bar(6, 45, 30, c=40)), EventType.BOS) == []       # close == level
    e2 = up_engine()
    assert types(e2.update(bar(6, 45, 30, c="40.1")), EventType.BOS)        # +1 pipette → kırılım


def test_ms_r007_new_low_box_includes_wick_below_old_range_candles():
    e = up_engine()
    e.update(bar(6, 50, 5, c=46))     # BOS mumunun kendi dibi (5) kutuya dahil
    assert e.state().swing_low.price == px(5) and e.state().swing_low.index == 6


@pytest.mark.parametrize("pullback,confirmed", [("38.4", False), ("43.7", True)])
def test_t_ms_06_07_h4_threshold_40(pullback, confirmed):
    h4 = StructureParams(PIP, D("40"), True, 2)
    e = StructureEngine(Timeframe.H4, h4)
    e.start(bars([(0, -5), (100, 50)]), Seed(Trend.BULL, 1, 0, False, Trend.BULL, 0))
    low = D("100") - D(pullback)
    evs = e.update(bar(2, 95, low, c=90))
    assert e.state().swing_high.confirmed is confirmed
    assert bool(types(evs, EventType.SWING_CONFIRMED)) is confirmed


@pytest.mark.parametrize("inclusive,confirmed", [(True, True), (False, False)])
def test_c06_exact_threshold_inclusive_flag(inclusive, confirmed):
    e = StructureEngine(Timeframe.H4, StructureParams(PIP, D("40"), inclusive, 2))
    e.start(bars([(0, -5), (100, 50)]), Seed(Trend.BULL, 1, 0, False, Trend.BULL, 0))
    e.update(bar(2, 95, 60, c=90))   # tam 40.0 pip
    assert e.state().swing_high.confirmed is confirmed


def test_ms_r008_new_high_resets_pullback_and_choch_does_not_confirm():
    e = engine(bars([(0, -5), (100, 50)]), Seed(Trend.BULL, 1, 0, False, Trend.BULL, 0), min_pips=40)
    e.update(bar(2, 95, 75, c=90))      # 25 pip geri çekilme
    e.update(bar(3, 110, 80, c=100))    # yeni uç → sıfırla
    e.update(bar(4, 105, 85, c=95))     # yeni uçtan 25 pip → onaylı değil
    st = e.state().swing_high
    assert st.price == px(110) and st.index == 3 and not st.confirmed


def test_ms_r009_trend_change_by_close_below_strong_low_and_spike_rule():
    e = up_engine()
    # wick ile strong low'un (0) altına, kapanış içeride → değişim yok
    assert types(e.update(bar(6, 38, -3, c=20)), EventType.BOS) == []
    assert e.state().swing_trend is Trend.BULL
    # spike: onaylı swing high'ın (40) wick ile aşılması (kapanış içeride)
    e2 = up_engine()
    e2.update(bar(6, 48, 30, c=38))
    evs = e2.update(bar(7, 36, -2, c="-1"))      # strong low'un altında KAPANIŞ
    (bos,) = types(evs, EventType.BOS)
    st = e2.state()
    assert bos.dir is Trend.BEAR and bos.level == px(0) and st.swing_trend is Trend.BEAR
    assert st.swing_high.price == px(48) and st.swing_high.strength is Strength.STRONG   # spike yeni swing high
    assert st.swing_low.price == px("-2") and st.swing_low.strength is Strength.WEAK and not st.swing_low.confirmed


def test_ms_r009_bearish_box_rule_and_bullish_flip_back():
    e = up_engine()
    e.update(bar(6, 36, -2, c="-1"))
    # bearish trend; yeni strong high 40 (idx2..6 arası max). Şimdi onaylı swing low oluştur
    for i, r in enumerate([(-10, -20, -15), (-5, -25, -22)], start=7):
        e.update(bar(i, *r[:2], c=r[2]))
    assert not e.state().swing_low.confirmed      # yeni dibin kendi mumundaki yükseliş geri çekilme sayılmaz
    e.update(bar(9, -12, -18, c=-14))              # dipten 13 pip yukarı ≥ 10 → onay
    assert e.state().swing_low.price == px(-25) and e.state().swing_low.confirmed
    evs = e.update(bar(10, 50, -10, c=45))        # strong high (40) üstünde kapanış → bullish trend değişimi
    (bos,) = types(evs, EventType.BOS)
    assert bos.dir is Trend.BULL and e.state().swing_trend is Trend.BULL


def test_closed_candles_only_and_order():
    e = up_engine()
    with pytest.raises(ValueError, match="KAPANMIŞ"):
        e.update(bar(6, 45, 30, complete=False))
    e.update(bar(6, 44, 30, c=35))
    with pytest.raises(ValueError, match="sıra"):
        e.update(bar(6, 44, 30, c=35))
    with pytest.raises(ValueError, match="TF"):
        e.update(bar(9, 44, 30, tf=Timeframe.M15))


def test_no_seed_no_events_cold_start_u15():
    e = StructureEngine(Timeframe.H4, params())
    assert e.update(bar(0, 10, 0)) == [] and e.state().swing_trend is Trend.UNDEFINED


def test_double_bos_not_coded_q_s05():
    with pytest.raises(NotImplementedError):
        StructureParams(PIP, D("10"), True, 2, "DOUBLE_BOS")


def test_inconsistent_seed_rejected():
    hist = bars(UP + [(50, 30, 46)])      # idx6 zaten BOS üretir
    with pytest.raises(ValueError, match="seed tutarsız"):
        engine(hist, UP_SEED)
    with pytest.raises(ValueError):
        engine(bars(UP), Seed(Trend.BULL, 0, 2, True, Trend.BULL, 0))   # uç, güçlü uçtan önce


def test_min_swing_candles_blocks_confirmation_when_range_too_short():
    e = StructureEngine(Timeframe.H4, StructureParams(PIP, D("10"), True, 3))
    e.start(bars([(0, -5), (30, 10)]), Seed(Trend.BULL, 1, 0, False, Trend.BULL, 0))  # aralık 2 mum < 3
    e.update(bar(2, 28, 15, c=20))
    assert not e.state().swing_high.confirmed


def test_eq_pd_r001_when_confirmed():
    e = up_engine()
    st = e.state()
    assert st.eq == px(20)     # low 0, high 40
    # BEAR tarafı
    assert up_engine().state().swing_low.kind is Kind.LOW


# ---------------- internal structure ----------------
# swing eşiği büyük tutulur ki swing olayları karışmasın
BIG = dict(min_pips=1000)
ISEED = Seed(Trend.BULL, 1, 0, False, Trend.BULL, 0)


def ie(rows, **kw):
    e = engine(bars(rows), ISEED, **{**BIG, **kw})
    return e


def test_t_ms_01_equal_high_makes_candidate_internal_high():
    e = ie([(5, 0), (10, 4)])
    e.update(bar(2, 20, 8))
    assert e.ipend is None
    e.update(bar(3, 20, 12))          # high eşit → pullback başladı
    assert e.ipend == (px(20), 2)


def test_t_ms_02_equal_low_is_not_choch_and_t_ms_03_wick_break_is():
    e = ie([(5, 0), (10, 4)])
    assert types(e.update(bar(2, 8, 0, c=5)), EventType.CHOCH) == []        # eşit → yok
    assert types(e.update(bar(3, 8, "0.0", c=6)), EventType.CHOCH) == []
    (ch,) = types(e.update(bar(4, 8, "-0.1", c=6)), EventType.CHOCH)         # 0.1 pip wick, kapanış yukarıda
    assert ch.dir is Trend.BEAR and ch.level == px(0) and not ch.by_close and ch.rule == "MS-R005"
    assert e.state().internal_trend is Trend.BEAR


def test_t_ms_08_low_that_broke_no_high_is_not_a_choch_reference():
    e = ie([(5, 0), (20, 8), (30, 18), (28, 12)])      # pullback; internal high (30) kırılmadı
    assert types(e.update(bar(4, 26, 7, c=10)), EventType.CHOCH) == []     # 8 altı ama 0 üstü: referans 0
    assert types(e.update(bar(5, 25, 3, c=8)), EventType.CHOCH) == []
    assert e.state().internal_low.price == px(0)
    assert types(e.update(bar(6, 24, -1, c=2)), EventType.CHOCH)


def test_ms_r003_nearest_low_not_lowest():
    rows = [(5, 0), (20, 8), (30, 18), (28, 12), (26, 9), (29, 14), (27, 11)]
    e = ie(rows)
    evs = e.update(bar(7, 31, 13, c=30))
    assert [x.type for x in evs] == [EventType.INTERNAL_REF]
    assert e.state().internal_low.price == px(11) and e.state().internal_low.index == 6   # en düşük (9) DEĞİL


def test_inside_bar_chain_uses_most_recent_inside_bar():
    # A(30,18) ... B,C inside bar zinciri; D yüksek kırar → en yakın aday = C (en son inside bar)
    rows = [(5, 0), (20, 8), (30, 18), (29, 19), (28, 20), (27, 21)]
    e = ie(rows)
    assert e.ipend == (px(30), 2)
    e.update(bar(6, 31, 21.5, c=30))
    assert e.state().internal_low.price == px(21) and e.state().internal_low.index == 5


def test_choch_only_first_break_and_new_reference_is_nearest_high():
    e = ie([(5, 0), (20, 8), (30, 18), (28, 12)])
    e.update(bar(4, 20, 14))
    (ch,) = types(e.update(bar(5, 18, -1, c=2)), EventType.CHOCH)
    # bearish internal; referans = en yakın internal high: bar4'ün high'ı (20) (bar5 onu kıramadı)
    st = e.state()
    assert st.internal_trend is Trend.BEAR and st.internal_high.price == px(20) and st.internal_high.index == 4
    # aynı yönde sonraki kırılım CHoCH değildir
    assert types(e.update(bar(6, 5, -10, c=-5)), EventType.CHOCH) == []
    # yukarı yönlü ilk kırılım (valid high 20 üstü) → bullish CHoCH
    assert types(e.update(bar(7, 21, -4, c=15)), EventType.CHOCH)


def test_outside_bar_unresolved_gives_no_signal_q_s04():
    e = ie([(5, 0), (20, 8), (30, 18), (28, 12)])
    before = (e.iref, e.ipend, e.e)
    evs = e.update(bar(4, 35, -3, c=10))                 # hem high'ı hem low'u kırdı, alt veri yok
    assert [x.type for x in evs] == [EventType.OUTSIDE_BAR] and evs[0].note == "UNRESOLVED"
    assert not any(x.signal_capable for x in evs)        # o mumdan sinyal yok
    assert (e.iref, e.ipend, e.e) == before and e.state().internal_trend is Trend.BULL


def m1(minute_offset, bar_idx, hi_pips=None, lo_pips=None):
    """bar_idx'inci H4 mumunun içinde bir M1 mum; yalnızca verilen uçlar uç değer, gövde ortada."""
    from photon.data import OHLC, QuoteCandle
    t = bar(bar_idx, 0, 0).open_time + timedelta(minutes=minute_offset)
    hi = px(hi_pips if hi_pips is not None else 20)
    lo = px(lo_pips if lo_pips is not None else 20)
    mid = px(20)
    o = OHLC(mid, max(hi, mid), min(lo, mid), mid)
    return QuoteCandle("EURUSD", Timeframe.M1, t, o, o)


def resolver(cands, ticks=None):
    from photon.data import PriceSide, SubTfResolver
    return SubTfResolver(cands, PriceSide.BID, ticks)


def ie_r(rows, res, **kw):
    e = StructureEngine(Timeframe.H4, params(**{**BIG, **kw}), resolver=res)
    e.start(bars(rows), ISEED)
    return e


def test_outside_bar_resolved_ref_first_gives_choch():
    res = resolver([m1(0, 4, lo_pips=-3), m1(1, 4, hi_pips=35)])         # önce low (ref), sonra high
    e = ie_r([(5, 0), (20, 8), (30, 18), (28, 12)], res)
    evs = e.update(bar(4, 35, -3, c=10))
    (ch,) = types(evs, EventType.CHOCH)
    assert ch.note == "OUTSIDE_BAR_RESOLVED" and ch.dir is Trend.BEAR and ch.signal_capable
    assert e.state().internal_trend is Trend.BEAR


def test_outside_bar_resolved_pend_first_updates_ref_then_choch():
    res = resolver([m1(0, 5, hi_pips=35), m1(1, 5, lo_pips=-3)])         # önce high (pend), sonra low
    e = ie_r([(5, 0), (20, 8), (30, 18), (28, 12), (26, 14)], res)
    evs = e.update(bar(5, 35, -3, c=10))
    assert [x.type for x in evs] == [EventType.INTERNAL_REF, EventType.CHOCH]
    assert evs[0].level == px(12) and evs[1].level == px(12) and evs[1].note == "OUTSIDE_BAR_RESOLVED"


def test_outside_bar_same_minute_needs_ticks_else_unresolved():
    from photon.data import Tick
    both = m1(0, 4, hi_pips=35, lo_pips=-3)                              # aynı dakikada ikisi de
    e = ie_r([(5, 0), (20, 8), (30, 18), (28, 12)], resolver([both]))
    assert [x.type for x in e.update(bar(4, 35, -3, c=10))] == [EventType.OUTSIDE_BAR]
    ticks = lambda a, b: [Tick("EURUSD", both.open_time, px(20), px(20.5)),
                          Tick("EURUSD", both.open_time + timedelta(seconds=5), px(-3), px(-2.5)),
                          Tick("EURUSD", both.open_time + timedelta(seconds=9), px(35), px(35.5))]
    e2 = ie_r([(5, 0), (20, 8), (30, 18), (28, 12)], resolver([both], ticks))
    (ch,) = types(e2.update(bar(4, 35, -3, c=10)), EventType.CHOCH)         # tick sırası: önce low
    assert ch.note == "OUTSIDE_BAR_RESOLVED"


def test_m1_engine_outside_bar_uses_ticks_only():
    from photon.data import PriceSide, SubTfResolver, Tick
    rows = [(5, 0), (20, 8), (30, 18), (28, 12)]
    t4 = bar(4, 0, 0, tf=Timeframe.M1).open_time
    ticks = lambda a, b: [Tick("EURUSD", t4, px(35), px(35.5)), Tick("EURUSD", t4 + timedelta(seconds=3), px(-3), px(-2.5))]
    e = StructureEngine(Timeframe.M1, params(**BIG), resolver=SubTfResolver([], PriceSide.BID, ticks))
    e.start(bars(rows, tf=Timeframe.M1), ISEED)
    evs = e.update(bar(4, 35, -3, c=10, tf=Timeframe.M1))
    assert [x.type for x in evs] == [EventType.CHOCH] and evs[0].note == "OUTSIDE_BAR_RESOLVED"   # tick: önce high, aday low yok → eski referans kırıldı


# ---------------- otomatik warm-up (Q-S01) ----------------
AUTO = [(10, 0), (20, 8), (30, 18), (25, 15), (22, 12)]


def auto_engine(live_from=None, **kw):
    e = StructureEngine(Timeframe.H4, params(**kw), live_from=live_from)
    e.start_auto()
    return e


def test_auto_trend_undefined_until_first_closed_swing_bos():
    e = auto_engine()
    for i, r in enumerate(AUTO):
        assert e.update(bar(i, *r)) == []
        assert e.state().swing_trend is Trend.UNDEFINED and not e.ready
    assert types(e.update(bar(5, 30, 20, c=30)), EventType.BOS) == []       # kapanış == swing high (30): kırılım değil
    evs = e.update(bar(6, 36, 28, c="30.1"))                                # +1 pipette kapanış → BOS
    (bos,) = types(evs, EventType.BOS)
    st = e.state()
    assert bos.dir is Trend.BULL and bos.level == px(30) and bos.note == "BOOTSTRAP"
    assert st.swing_trend is Trend.BULL and st.swing_low.price == px(12) and st.swing_low.index == 4   # kutu kuralı
    assert st.internal_trend is Trend.BULL and e.ready


def test_auto_wick_only_above_swing_high_is_not_bos_and_unconfirmed_high_just_extends():
    e = auto_engine()
    for i, r in enumerate(AUTO):
        e.update(bar(i, *r))
    assert e.update(bar(5, 33, 20, c=29)) == []        # wick geçti, kapanış içeride → sweep
    e2 = auto_engine()
    for i, r in enumerate([(10, 0), (20, 8), (30, 18)]):
        e2.update(bar(i, *r))
    assert e2.update(bar(3, 40, 25, c=39)) == []       # swing high henüz onaysız → yalnız uç uzar
    assert e2.state().swing_trend is Trend.UNDEFINED


def test_auto_bearish_bootstrap_and_internal_ref():
    rows = [(0, -10), (12, 2), (20, 10), (14, 6), (4, -2)]            # düşüş: önce tepe, sonra dip onayı
    e = auto_engine()
    for i, r in enumerate([(30, 20), (28, 12), (18, 6), (22, 10), (24, 14)]):
        assert e.update(bar(i, *r)) == []
    evs = e.update(bar(5, 17, 4, c=4))                                 # dip (6) altında kapanış
    (bos,) = types(evs, EventType.BOS)
    assert bos.dir is Trend.BEAR and e.state().swing_trend is Trend.BEAR


def test_warmup_events_flagged_and_dont_signal():
    live = bar(7, 0, 0).open_time
    e = auto_engine(live_from=live)
    for i, r in enumerate(AUTO):
        e.update(bar(i, *r))
    (bos,) = types(e.update(bar(5, 36, 28, c="30.1")), EventType.BOS)
    assert bos.warmup and not bos.signal_capable and not e.ready         # warm-up içinde
    e.update(bar(6, 38, 30, c=36))
    assert not e.ready
    evs = e.update(bar(7, 40, 30, c=39))
    assert e.ready and all(not x.warmup for x in evs)


def test_manual_seed_option_still_works_and_is_not_warmup():
    e = up_engine()
    (bos,) = types(e.update(bar(6, 45, 30, c=42)), EventType.BOS)
    assert not bos.warmup and bos.signal_capable and e.ready


def test_start_auto_after_start_rejected():
    e = up_engine()
    with pytest.raises(RuntimeError):
        e.start_auto()


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_mirror_symmetry_auto_warmup(seed):
    rnd = random.Random(seed)
    rows = random_series(500, rnd)
    cs = [bar(i, h, l, c) for i, (h, l, c) in enumerate(rows)]
    k = D("2.2000")
    a, b = auto_engine(min_pips=15), auto_engine(min_pips=15)
    for c in cs:
        a.update(c)
        b.update(mirror(c, k))
    flip = {Trend.BULL: Trend.BEAR, Trend.BEAR: Trend.BULL, Trend.UNDEFINED: Trend.UNDEFINED}
    ea = [(x.type, x.dir, x.level, x.break_index, x.note) for x in a.events]
    eb = [(x.type, flip[x.dir], k - x.level, x.break_index, x.note) for x in b.events]
    assert ea == eb and a.state().swing_trend is flip[b.state().swing_trend]
    assert a.events and a.events[0].note == "BOOTSTRAP"


def test_warmup_config_and_gate():
    cfg = load_config()
    cfg.require("structure_warmup")
    assert cfg.get("warmup_period") == {"D1": 365, "H4": 365, "M15": 30, "M1": 7}


# ---------------- simetri: aynalanmış veri → aynalanmış olaylar ----------------
def mirror(c: Candle, k: D) -> Candle:
    return Candle(c.pair, c.tf, c.open_time, k - c.open, k - c.low, k - c.high, k - c.close, c.complete)


def random_series(n, rnd):
    price, out = D("30"), []
    for i in range(n):
        step = D(rnd.randint(-9, 9))
        o = price
        c = price + step
        h = max(o, c) + D(rnd.randint(0, 5))
        l = min(o, c) - D(rnd.randint(0, 5))
        out.append((h, l, c))
        price = c
    return out


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_mirror_symmetry(seed):
    rnd = random.Random(seed)
    rows = [(10, 0, 5), (20, 8, 15)] + random_series(400, rnd)
    hist, rest = bars([(h, l, c) for h, l, c in rows[:2]]), [bar(i + 2, h, l, c) for i, (h, l, c) in enumerate(rows[2:])]
    k = D("2.2000")
    a = StructureEngine(Timeframe.H4, params(min_pips=15))
    a.start(hist, Seed(Trend.BULL, 1, 0, False, Trend.BULL, 0))
    b = StructureEngine(Timeframe.H4, params(min_pips=15))
    b.start([mirror(c, k) for c in hist], Seed(Trend.BEAR, 0, 1, False, Trend.BEAR, 0))
    for c in rest:
        a.update(c)
        b.update(mirror(c, k))
    flip = {Trend.BULL: Trend.BEAR, Trend.BEAR: Trend.BULL}
    ea = [(x.type, x.dir, x.level, x.break_index, x.note) for x in a.events]
    eb = [(x.type, flip[x.dir], k - x.level, x.break_index, x.note) for x in b.events]
    assert ea == eb
    kinds = {x.type for x in a.events}
    assert EventType.BOS in kinds and EventType.CHOCH in kinds     # senaryo gerçekten olay üretiyor
    assert a.state().swing_trend is flip[b.state().swing_trend]


def test_determinism():
    rnd = random.Random(9)
    rows = random_series(300, rnd)

    def run():
        e = StructureEngine(Timeframe.H4, params(min_pips=15))
        e.start(bars([(10, 0, 5), (20, 8, 15)]), Seed(Trend.BULL, 1, 0, False, Trend.BULL, 0))
        for i, (h, l, c) in enumerate(rows):
            e.update(bar(i + 2, h, l, c))
        return [(x.type, x.dir, x.level, x.break_index) for x in e.events]
    assert run() == run()


# ---------------- config ----------------
def test_params_from_config():
    cfg = load_config()
    p = StructureParams.from_config(cfg, "EURUSD", Timeframe.H4)
    assert p.min_pullback_pips == 40 and p.threshold_inclusive and p.pip_size == PIP and p.min_swing_candles == 2
    assert StructureParams.from_config(cfg, "EURUSD", Timeframe.D1).min_pullback_pips == 90
    assert StructureParams.from_config(cfg, "EURUSD", Timeframe.M15).min_pullback_pips == 15
    with pytest.raises(ConfigError, match="swing_min_pullback_pips.EURUSD.M1"):
        StructureParams.from_config(cfg, "EURUSD", Timeframe.M1)


# ---------------- rapor çıktıları ----------------
def test_csv_and_chart_and_seed_yaml(tmp_path):
    from photon.structure.report import load_seed_yaml, plot_events, run_structure, write_events_csv
    rows = UP + [(45, 30, 42), (44, 35, 41)]
    cs = bars(rows)
    seedf = tmp_path / "seed.yaml"
    t = lambda i: cs[i].open_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    seedf.write_text(f"swing_trend: BULL\nswing_high_time: '{t(2)}'\nswing_low_time: '{t(0)}'\n"
                     f"swing_high_confirmed: true\ninternal_trend: BULL\ninternal_ref_time: '{t(0)}'\n")
    seed, hist = load_seed_yaml(seedf, cs)
    assert seed == UP_SEED and hist == 3
    eng = run_structure(cs, params(), seed, hist)
    n = write_events_csv(eng.events, tmp_path / "e.csv")
    assert n == len(eng.events) >= 2
    header, *lines = (tmp_path / "e.csv").read_text().splitlines()
    assert header.startswith("time_utc,tf,type,dir,level") and any(",BOS,BULL," in l for l in lines)
    plot_events(cs, eng.events, tmp_path / "e.png")
    assert (tmp_path / "e.png").stat().st_size > 1000
