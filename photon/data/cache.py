"""Yerel önbellek (SQLite, stdlib). Fiyatlar TEXT (Decimal birebir), zaman UTC epoch saniye.

`candles`: kaynak+parite+TF bazlı bid/ask mumları. `chunks`: indirilen parçalar (kesintide kaldığı
yerden devam). Boş (veri yok) parçalar da kaydedilir ki tekrar istenmesin.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator

from .models import OHLC, QuoteCandle, Timeframe
from .tz import UTC

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
  source TEXT NOT NULL, pair TEXT NOT NULL, tf TEXT NOT NULL, t INTEGER NOT NULL,
  bo TEXT, bh TEXT, bl TEXT, bc TEXT, ao TEXT, ah TEXT, al TEXT, ac TEXT,
  n_ticks INTEGER, complete INTEGER NOT NULL,
  PRIMARY KEY (source, pair, tf, t));
CREATE TABLE IF NOT EXISTS chunks (
  source TEXT NOT NULL, pair TEXT NOT NULL, key TEXT NOT NULL, status TEXT NOT NULL,
  PRIMARY KEY (source, pair, key));
"""


def _ts(dt: datetime) -> int:
    return int(dt.astimezone(UTC).timestamp())


class CandleStore:
    def __init__(self, path: str | Path):
        p = Path(path)
        if str(path) != ":memory:":
            p.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def put_candles(self, source: str, candles: Iterable[QuoteCandle]) -> int:
        rows = [(source, c.pair, c.tf.value, _ts(c.open_time),
                 *(str(x) for x in (c.bid.open, c.bid.high, c.bid.low, c.bid.close,
                                    c.ask.open, c.ask.high, c.ask.low, c.ask.close)),
                 c.n_ticks, int(c.complete)) for c in candles]
        with self._db:
            self._db.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)

    def get_candles(self, source: str, pair: str, tf: Timeframe,
                    start: datetime, end: datetime) -> Iterator[QuoteCandle]:
        """[start, end) aralığı, zaman sıralı."""
        cur = self._db.execute(
            "SELECT t,bo,bh,bl,bc,ao,ah,al,ac,n_ticks,complete FROM candles "
            "WHERE source=? AND pair=? AND tf=? AND t>=? AND t<? ORDER BY t",
            (source, pair, tf.value, _ts(start), _ts(end)))
        for t, *p, n, comp in cur:
            d = [Decimal(x) for x in p]
            yield QuoteCandle(pair, tf, datetime.fromtimestamp(t, UTC), OHLC(*d[:4]), OHLC(*d[4:]), bool(comp), n)

    def chunk_status(self, source: str, pair: str, key: str) -> str | None:
        r = self._db.execute("SELECT status FROM chunks WHERE source=? AND pair=? AND key=?",
                             (source, pair, key)).fetchone()
        return r[0] if r else None

    def mark_chunk(self, source: str, pair: str, key: str, status: str) -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?)", (source, pair, key, status))
