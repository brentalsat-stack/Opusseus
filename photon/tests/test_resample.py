from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from photon.data import BoundarySpec, MinuteAggregator, Timeframe, bin_bounds, resample, ticks_to_m1
from photon.tests.helpers import UTC, qc, tick

NY = BoundarySpec(ZoneInfo("America/New_York"), time(17, 0), time(17, 0))


def test_ticks_to_m1_ohlc_bid_ask_and_no_gap_fill():
    t0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
    ticks = [tick(t0, "1.1000"), tick(t0 + timedelta(seconds=10), "1.1005"),
             tick(t0 + timedelta(seconds=20), "1.0995"), tick(t0 + timedelta(seconds=59), "1.1002"),
             tick(t0 + timedelta(minutes=3), "1.1010")]
    out = list(ticks_to_m1(ticks))
    assert [c.open_time.minute for c in out] == [0, 3]          # 1-2. dakika doldurulmaz
    c = out[0]
    assert (c.bid.open, c.bid.high, c.bid.low, c.bid.close) == (D("1.1000"), D("1.1005"), D("1.0995"), D("1.1002"))
    assert c.ask.high == D("1.1006") and c.n_ticks == 4


def test_ticks_out_of_order_raises():
    t0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        list(ticks_to_m1([tick(t0 + timedelta(seconds=5), "1.1"), tick(t0, "1.1")]))


def test_m1_to_m15_values():
    t0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
    cs = [qc(t0 + timedelta(minutes=i), bid=(f"1.10{i:02d}", f"1.10{i:02d}", f"1.10{i:02d}", f"1.10{i:02d}"),
             n_ticks=2) for i in range(15)]
    cs[7] = qc(cs[7].open_time, bid=("1.1007", "1.1500", "1.0500", "1.1007"), n_ticks=2)
    (m15,) = resample(cs + [qc(t0 + timedelta(minutes=15))], Timeframe.M15)[:1]
    assert m15.open_time == t0 and m15.bid.open == D("1.1000") and m15.bid.close == D("1.1014")
    assert m15.bid.high == D("1.1500") and m15.bid.low == D("1.0500") and m15.n_ticks == 30 and m15.complete


def test_last_bin_incomplete_and_gaps_not_filled():
    t0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
    cs = [qc(t0 + timedelta(minutes=i)) for i in (0, 1, 2, 5)]      # eksik dakikalar doldurulmaz
    (m15,) = resample(cs, Timeframe.M15)
    assert not m15.complete and m15.bid.close == cs[-1].bid.close


def test_unsorted_or_duplicate_input_raises():
    t0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        resample([qc(t0 + timedelta(minutes=1)), qc(t0)], Timeframe.M15)
    with pytest.raises(ValueError):
        resample([qc(t0), qc(t0)], Timeframe.M15)


def test_resample_requires_coarser_tf():
    t0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        resample([qc(t0)], Timeframe.M1)


def test_h4_d1_need_spec():
    with pytest.raises(ValueError):
        bin_bounds(datetime(2021, 9, 1, tzinfo=UTC), Timeframe.D1, None)


@pytest.mark.parametrize("ts,start,end", [
    # yaz saati (EDT, UTC-4): gün 21:00Z'de açılır
    (datetime(2021, 9, 1, 12, 0, tzinfo=UTC), datetime(2021, 8, 31, 21, 0, tzinfo=UTC), datetime(2021, 9, 1, 21, 0, tzinfo=UTC)),
    (datetime(2021, 9, 1, 21, 0, tzinfo=UTC), datetime(2021, 9, 1, 21, 0, tzinfo=UTC), datetime(2021, 9, 2, 21, 0, tzinfo=UTC)),
    # kış saati (EST, UTC-5): 22:00Z
    (datetime(2021, 12, 1, 12, 0, tzinfo=UTC), datetime(2021, 11, 30, 22, 0, tzinfo=UTC), datetime(2021, 12, 1, 22, 0, tzinfo=UTC)),
    # ilkbahar geçişi (14 Mart 2021): 13 Mart 22:00Z → 14 Mart 21:00Z = 23 saatlik gün
    (datetime(2021, 3, 14, 10, 0, tzinfo=UTC), datetime(2021, 3, 13, 22, 0, tzinfo=UTC), datetime(2021, 3, 14, 21, 0, tzinfo=UTC)),
    # sonbahar geçişi (7 Kasım 2021): 6 Kasım 21:00Z → 7 Kasım 22:00Z = 25 saatlik gün
    (datetime(2021, 11, 7, 10, 0, tzinfo=UTC), datetime(2021, 11, 6, 21, 0, tzinfo=UTC), datetime(2021, 11, 7, 22, 0, tzinfo=UTC)),
])
def test_d1_bounds_across_dst(ts, start, end):
    assert bin_bounds(ts, Timeframe.D1, NY) == (start, end)
    assert (end - start) in (timedelta(hours=23), timedelta(hours=24), timedelta(hours=25))


def test_h4_bins_aligned_to_anchor_and_reset_on_short_day():
    s, e = bin_bounds(datetime(2021, 9, 1, 2, 0, tzinfo=UTC), Timeframe.H4, NY)   # 21:00Z'e hizalı
    assert (s, e) == (datetime(2021, 9, 1, 1, 0, tzinfo=UTC), datetime(2021, 9, 1, 5, 0, tzinfo=UTC))
    # 23 saatlik gün: son H4 kutusu 3 saat
    s, e = bin_bounds(datetime(2021, 3, 14, 20, 0, tzinfo=UTC), Timeframe.H4, NY)
    assert (s, e) == (datetime(2021, 3, 14, 18, 0, tzinfo=UTC), datetime(2021, 3, 14, 21, 0, tzinfo=UTC))


def test_h4_and_d1_resample_from_m15():
    t0 = datetime(2021, 9, 1, 21, 0, tzinfo=UTC)
    m15 = [qc(t0 + timedelta(minutes=15 * i), tf=Timeframe.M15) for i in range(96 * 1 + 4)]
    h4 = resample(m15, Timeframe.H4, NY)
    d1 = resample(m15, Timeframe.D1, NY)
    assert h4[0].open_time == t0 and h4[1].open_time == t0 + timedelta(hours=4)
    assert d1[0].open_time == t0 and d1[1].open_time == t0 + timedelta(hours=24) and not d1[1].complete


def test_misaligned_anchor_rejected():
    odd = BoundarySpec(ZoneInfo("America/New_York"), time(17, 7), time(17, 7))
    t0 = datetime(2021, 9, 1, 21, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        resample([qc(t0 + timedelta(minutes=15 * i), tf=Timeframe.M15) for i in range(8)], Timeframe.H4, odd)


def test_minute_aggregator_emits_on_rollover():
    t0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)
    agg = MinuteAggregator()
    assert agg.feed(tick(t0, "1.1")) == []
    assert agg.feed(tick(t0 + timedelta(seconds=30), "1.2")) == []
    out = agg.feed(tick(t0 + timedelta(seconds=61), "1.15"))
    assert len(out) == 1 and out[0].bid.high == D("1.2") and out[0].open_time == t0
