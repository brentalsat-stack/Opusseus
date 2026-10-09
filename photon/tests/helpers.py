from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from photon.data import OHLC, QuoteCandle, Tick, Timeframe

UTC = timezone.utc


def qc(t, bid=("1.1000", "1.1002", "1.0998", "1.1001"), spread="0.0001", tf=Timeframe.M1, **kw):
    b = [D(x) for x in bid]
    a = [x + D(spread) for x in b]
    return QuoteCandle("EURUSD", tf, t, OHLC(*b), OHLC(*a), **kw)


def minutes(start, n, step=1):
    return [start + timedelta(minutes=step * i) for i in range(n)]


def tick(t, bid, ask=None):
    bid = D(bid)
    return Tick("EURUSD", t, bid, D(ask) if ask else bid + D("0.0001"))
