"""OANDA v20 practice API — M1 bid/ask mumları (price=BA). Jeton ortam değişkeninden okunur (config'e yazılmaz).

Yalnızca okuma uç noktası (`/v3/instruments/{enstrüman}/candles`); hesap/emir uç noktaları kullanılmaz.
H4/D1'i OANDA'dan çekmiyoruz: kendi sınır kuralımızla M1'den resample edilir (Q-D01).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from ..cache import CandleStore
from ..models import OHLC, QuoteCandle, Timeframe
from ..tz import UTC
from .http import HttpGet, default_get, get_with_retry

log = logging.getLogger(__name__)
SOURCE = "OANDA_PRACTICE"
PAGE = 5000  # OANDA count üst sınırı


def _parse_time(s: str) -> datetime:
    head, _, frac = s.rstrip("Z").partition(".")
    micro = (frac + "000000")[:6]
    return datetime.strptime(f"{head}.{micro}", "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC)


def parse_candle(pair: str, c: dict) -> QuoteCandle:
    def ohlc(d: dict) -> OHLC:
        return OHLC(Decimal(d["o"]), Decimal(d["h"]), Decimal(d["l"]), Decimal(d["c"]))
    return QuoteCandle(pair, Timeframe.M1, _parse_time(c["time"]), ohlc(c["bid"]), ohlc(c["ask"]),
                       bool(c["complete"]), int(c["volume"]))


class OandaClient:
    def __init__(self, rest_host: str, token_env: str, max_retries: int = 5,
                 http_get: HttpGet = default_get, sleep: Callable[[float], None] = time.sleep):
        token = os.environ.get(token_env)
        if not token:
            raise RuntimeError(f"OANDA jetonu yok: ortam değişkeni {token_env} tanımlı değil")
        self.host, self._token, self.max_retries = rest_host, token, max_retries
        self._get, self._sleep = http_get, sleep

    def fetch_m1(self, pair: str, instrument: str, start: datetime, end: datetime) -> list[QuoteCandle]:
        """[start, end) M1 bid/ask mumları. Tamamlanmamış (complete=false) mumlar dahil EDİLMEZ."""
        out: list[QuoteCandle] = []
        cursor = start.astimezone(UTC)
        while cursor < end:
            q = urllib.parse.urlencode({"price": "BA", "granularity": "M1", "count": PAGE,
                                        "from": cursor.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")})
            url = f"https://{self.host}/v3/instruments/{instrument}/candles?{q}"
            status, body = get_with_retry(url, {"Authorization": f"Bearer {self._token}"},
                                          self._get, self.max_retries, self._sleep)
            if status != 200:
                raise RuntimeError(f"OANDA {status}: {body[:200]!r}")
            raw = json.loads(body).get("candles", [])
            if not raw:
                break
            out += [c for c in (parse_candle(pair, x) for x in raw if x["complete"]) if c.open_time < end]
            last = _parse_time(raw[-1]["time"])
            if len(raw) < PAGE or last + timedelta(minutes=1) >= end:
                break
            cursor = last + timedelta(minutes=1)
        return out

    def download_m1(self, pair: str, instrument: str, start: datetime, end: datetime, store: CandleStore) -> int:
        n = 0
        day = start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        while day < end:
            key = f"{day:%Y%m%d}"
            if store.chunk_status(SOURCE, pair, key) is None:
                candles = self.fetch_m1(pair, instrument, max(day, start), min(day + timedelta(days=1), end))
                n += store.put_candles(SOURCE, candles)
                if day >= start and day + timedelta(days=1) <= end:  # yalnızca tam gün parçası kaydedilir
                    store.mark_chunk(SOURCE, pair, key, "OK" if candles else "EMPTY")
            day += timedelta(days=1)
        return n
