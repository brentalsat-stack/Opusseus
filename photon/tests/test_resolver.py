from datetime import timedelta
from decimal import Decimal as D

from photon.data import OHLC, PriceSide, QuoteCandle, SubTfResolver, Tick, Timeframe
from photon.tests.helpers import UTC
from datetime import datetime

T0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
PIPETTE = D("0.00001")


def m1(minute, hi, lo):
    o = OHLC(D("1.1000"), D(hi), D(lo), D("1.1000"))
    return QuoteCandle("EURUSD", Timeframe.M1, T0 + timedelta(minutes=minute), o, o)


def test_first_touch_orders_by_m1():
    r = SubTfResolver([m1(0, "1.1000", "1.0990"), m1(1, "1.1020", "1.1000")], PriceSide.BID)
    assert r.first_touch(Timeframe.M15, T0, D("1.1010"), D("1.0995"), PIPETTE) == "DOWN"
    r = SubTfResolver([m1(0, "1.1020", "1.1000"), m1(1, "1.1000", "1.0990")], PriceSide.BID)
    assert r.first_touch(Timeframe.M15, T0, D("1.1010"), D("1.0995"), PIPETTE) == "UP"


def test_equality_is_not_a_touch_and_window_is_respected():
    r = SubTfResolver([m1(0, "1.1010", "1.0995")], PriceSide.BID)            # tam eşit
    assert r.first_touch(Timeframe.M15, T0, D("1.1010"), D("1.0995"), PIPETTE) is None
    r = SubTfResolver([m1(20, "1.1050", "1.0900")], PriceSide.BID)            # M15 penceresi dışında
    assert r.first_touch(Timeframe.M15, T0, D("1.1010"), D("1.0995"), PIPETTE) is None


def test_same_minute_goes_to_ticks_or_none():
    both = m1(0, "1.1020", "1.0990")
    assert SubTfResolver([both], PriceSide.BID).first_touch(Timeframe.M15, T0, D("1.1010"), D("1.0995"), PIPETTE) is None
    ticks = lambda a, b: [Tick("EURUSD", T0, D("1.0990"), D("1.0991")), Tick("EURUSD", T0, D("1.1020"), D("1.1021"))]
    assert SubTfResolver([both], PriceSide.BID, ticks).first_touch(Timeframe.M15, T0, D("1.1010"), D("1.0995"), PIPETTE) == "DOWN"
    # tick sağlayıcı veri döndürmezse çözülemez
    assert SubTfResolver([both], PriceSide.BID, lambda a, b: None).first_touch(Timeframe.M15, T0, D("1.1010"), D("1.0995"), PIPETTE) is None


def test_ask_side():
    o = OHLC(D("1.1000"), D("1.1000"), D("1.1000"), D("1.1000"))
    ask = OHLC(D("1.1001"), D("1.1030"), D("1.1001"), D("1.1001"))
    c = QuoteCandle("EURUSD", Timeframe.M1, T0, o, ask)
    assert SubTfResolver([c], PriceSide.ASK).first_touch(Timeframe.M15, T0, D("1.1020"), D("1.0900"), PIPETTE) == "UP"
    assert SubTfResolver([c], PriceSide.BID).first_touch(Timeframe.M15, T0, D("1.1020"), D("1.0900"), PIPETTE) is None
