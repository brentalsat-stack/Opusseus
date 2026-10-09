from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from photon.data import Candle, Timeframe

T = datetime(2021, 9, 1, tzinfo=timezone.utc)


def mk(**kw):
    base = dict(pair="EURUSD", tf=Timeframe.M1, open_time=T, open=D("1.1800"), high=D("1.1805"),
                low=D("1.1795"), close=D("1.1802"))
    return Candle(**{**base, **kw})


def test_valid():
    assert mk().close == D("1.1802")


def test_float_rejected():
    with pytest.raises(TypeError):
        mk(open=1.18)


def test_naive_and_non_utc_time_rejected():
    with pytest.raises(ValueError):
        mk(open_time=datetime(2021, 9, 1))
    with pytest.raises(ValueError):
        mk(open_time=T.astimezone(timezone(timedelta(hours=3))))


def test_inconsistent_ohlc_rejected():
    with pytest.raises(ValueError):
        mk(high=D("1.1790"))
    with pytest.raises(ValueError):
        mk(low=D("1.1801"))


def test_non_positive_rejected():
    with pytest.raises(ValueError):
        mk(low=D("0"))
