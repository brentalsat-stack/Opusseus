"""Dukascopy tick arşivi indiricisi (hesap gerektirmez). Ham .bi5 dosyaları diskte önbelleklenir.

URL: {base}/{SEMBOL}/{YYYY}/{AA-1:02d}/{GG}/{SS}h_ticks.bi5  (ay 0 tabanlı, saat UTC)
Kayıt (20 bayt, big-endian): uint32 ms_offset, uint32 ask, uint32 bid, float32 ask_vol, float32 bid_vol
Fiyat = tamsayı / ölçek; ölçek = 1 / (pip_size/10)  (EURUSD: 1e5).
"""
from __future__ import annotations

import logging
import lzma
import struct
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterator

from ..cache import CandleStore
from ..models import Tick
from ..resample import ticks_to_m1
from ..tz import UTC
from .http import HttpGet, default_get, get_with_retry

log = logging.getLogger(__name__)
SOURCE = "DUKASCOPY"
_REC = struct.Struct(">IIIff")


def hour_url(base: str, symbol: str, hour: datetime) -> str:
    return f"{base.rstrip('/')}/{symbol}/{hour.year}/{hour.month - 1:02d}/{hour.day:02d}/{hour.hour:02d}h_ticks.bi5"


def decode_ticks(data: bytes, pair: str, hour: datetime, pip_size: Decimal) -> list[Tick]:
    """bi5 baytlarını Tick listesine çevirir. Boş bayt → boş liste. Bozuk uzunluk → hata."""
    if not data:
        return []
    raw = lzma.LZMADecompressor(format=lzma.FORMAT_AUTO).decompress(data)
    if len(raw) % _REC.size:
        raise ValueError(f"{hour}: bi5 uzunluğu {len(raw)} 20'nin katı değil")
    scale = Decimal(10) / pip_size  # ondalık pip çözünürlüğü
    out = []
    for off in range(0, len(raw), _REC.size):
        ms, ask, bid, _av, _bv = _REC.unpack_from(raw, off)
        out.append(Tick(pair, hour + timedelta(milliseconds=ms), Decimal(bid) / scale, Decimal(ask) / scale))
    return out


class DukascopyClient:
    def __init__(self, base_url: str, raw_dir: str | Path, request_delay_s: float, max_retries: int,
                 http_get: HttpGet = default_get, sleep: Callable[[float], None] = time.sleep):
        self.base, self.raw_dir = base_url, Path(raw_dir)
        self.delay, self.max_retries = request_delay_s, max_retries
        self._get, self._sleep = http_get, sleep

    def _raw_path(self, symbol: str, hour: datetime) -> Path:
        return self.raw_dir / SOURCE / symbol / f"{hour:%Y%m%d_%H}.bi5"

    def fetch_hour(self, symbol: str, hour: datetime) -> bytes:
        """Ham bi5 baytları (404 = o saatte veri yok → b''). Diskte önbelleklenir; ağ isteği aralıklıdır."""
        path = self._raw_path(symbol, hour)
        if path.exists():
            return path.read_bytes()
        self._sleep(self.delay)
        status, body = get_with_retry(hour_url(self.base, symbol, hour), {}, self._get, self.max_retries, self._sleep)
        data = b"" if status == 404 else body
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return data

    def download_m1(self, pair: str, symbol: str, pip_size: Decimal, start: datetime, end: datetime,
                    store: CandleStore) -> int:
        """[start, end) için saat saat indirir, M1'e çevirir, önbelleğe yazar (devam edilebilir).
        Döner: yazılan M1 mum sayısı."""
        n = 0
        hour = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        while hour < end:
            key = f"{hour:%Y%m%d%H}"
            if store.chunk_status(SOURCE, pair, key) is None:
                data = self.fetch_hour(symbol, hour)
                ticks = decode_ticks(data, pair, hour, pip_size)
                n += store.put_candles(SOURCE, ticks_to_m1(ticks))
                store.mark_chunk(SOURCE, pair, key, "EMPTY" if not ticks else "OK")
                log.debug("dukascopy %s %s: %d tick", pair, key, len(ticks))
            hour += timedelta(hours=1)
        return n


def iter_hours(start: datetime, end: datetime) -> Iterator[datetime]:
    h = start.replace(minute=0, second=0, microsecond=0)
    while h < end:
        yield h
        h += timedelta(hours=1)
