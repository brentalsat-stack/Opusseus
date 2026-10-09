"""IBKR canlı bid/ask akışı (ib_async). YALNIZCA OKUMA: bağlantı readonly=True; emir API'si kullanılmaz.

`ib_async` yalnızca burada, çalışma anında import edilir (kurulu değilse açık hata).
Test edilemeyen kısım broker bağlantısıdır; tick→Tick dönüşümü `to_tick` ile ayrıca test edilir.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import AsyncIterator

from ..models import Tick
from ..tz import UTC

log = logging.getLogger(__name__)


def to_tick(pair: str, bid: float, ask: float, when: datetime, pip_size: Decimal) -> Tick | None:
    """IB float fiyatlarını Decimal'e çevirir (ondalık pip çözünürlüğüne yuvarlar). Geçersiz (nan/≤0) → None."""
    if not (bid and ask) or bid != bid or ask != ask or bid <= 0 or ask <= 0:
        return None
    q = pip_size / 10
    return Tick(pair, when.astimezone(UTC), Decimal(repr(bid)).quantize(q), Decimal(repr(ask)).quantize(q))


class IbkrQuoteFeed:
    def __init__(self, host: str, port: int, client_id: int, pair: str, symbol: str, venue: str,
                 pip_size: Decimal):
        self.host, self.port, self.client_id = host, port, client_id
        self.pair, self.symbol, self.venue, self.pip_size = pair, symbol, venue, pip_size

    async def ticks(self) -> AsyncIterator[Tick]:
        try:
            from ib_async import IB, Forex
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("ib_async kurulu değil: pip install ib_async") from e
        ib = IB()
        await ib.connectAsync(self.host, self.port, clientId=self.client_id, readonly=True)
        q: asyncio.Queue[Tick] = asyncio.Queue()
        ticker = ib.reqMktData(Forex(self.symbol.replace(".", ""), exchange=self.venue), "", False, False)

        def on_update(t) -> None:
            tick = to_tick(self.pair, t.bid, t.ask, t.time, self.pip_size)
            if tick:
                q.put_nowait(tick)

        ticker.updateEvent += on_update
        try:
            while True:
                yield await q.get()
        finally:  # pragma: no cover
            ticker.updateEvent -= on_update
            ib.cancelMktData(ticker.contract)
            ib.disconnect()
