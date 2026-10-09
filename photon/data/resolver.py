"""Outside bar sırasının alt TF verisiyle çözümü (Q-S04): M15→M1, M1→tick.

Soru: bir mumun içinde `up_level` yukarı mı, `down_level` aşağı mı (≥ 1 pipette) önce kırıldı?
Alt veri yoksa veya aynı alt mum/tick her ikisini de kırıyorsa → None (çözülemedi; varsayım YAPILMAZ).
"""
from __future__ import annotations

from bisect import bisect_left
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional, Sequence

from .models import PriceSide, QuoteCandle, Tick, Timeframe

TickProvider = Callable[[datetime, datetime], Optional[Sequence[Tick]]]


class SubTfResolver:
    def __init__(self, m1: Sequence[QuoteCandle], side: PriceSide,
                 ticks: TickProvider | None = None):
        """`m1`: zaman sıralı M1 mumları (yapı motoruyla AYNI fiyat tarafı: `side`)."""
        self._m1, self._times, self._side, self._ticks = list(m1), [c.open_time for c in m1], PriceSide(side), ticks

    def first_touch(self, tf: Timeframe, open_time: datetime, up_level: Decimal,
                    down_level: Decimal, pipette: Decimal) -> Optional[str]:
        end = open_time + tf.delta
        if tf is Timeframe.M1:
            return self._by_ticks(open_time, end, up_level, down_level, pipette)
        lo, hi = bisect_left(self._times, open_time), bisect_left(self._times, end)
        for c in self._m1[lo:hi]:
            ohlc = c.bid if self._side is PriceSide.BID else c.ask
            up, down = ohlc.high - up_level >= pipette, down_level - ohlc.low >= pipette
            if up and down:   # aynı dakika → tick
                return self._by_ticks(c.open_time, c.open_time + Timeframe.M1.delta, up_level, down_level, pipette)
            if up:
                return "UP"
            if down:
                return "DOWN"
        return None

    def _by_ticks(self, start, end, up_level, down_level, pipette) -> Optional[str]:
        if self._ticks is None:
            return None
        ticks = self._ticks(start, end)
        if not ticks:
            return None
        for t in ticks:
            p = t.bid if self._side is PriceSide.BID else t.ask
            if p - up_level >= pipette:
                return "UP"
            if down_level - p >= pipette:
                return "DOWN"
        return None
