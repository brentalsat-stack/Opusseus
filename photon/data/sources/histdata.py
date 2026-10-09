"""HistData.com içe aktarıcı: EURUSD M1 **bid** (ASCII). Dosya kaynaklı veri (ağ yok).

Format (başlıksız, ayraç ';'): `YYYYMMDD HHMMSS;Open;High;Low;Close;Volume` — hacim 0 (yok sayılır).
Saat: sabit EST = UTC−5, DST YOK (DECISIONS §7) → önce UTC'ye çevrilir; NY 17:00 mum sınırları sonra zoneinfo ile hesaplanır.
Veri yalnız bid: ask = bid + sabit spread (costs.spread_pips = 0.4, kullanıcı kararı).
Hatalı/tekrarlı/sırasız satırlar sessizce düzeltilmez: sayılır, loglanır ve raporda gösterilir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from ..cache import CandleStore
from ..models import OHLC, QuoteCandle, Timeframe
from ..tz import UTC

log = logging.getLogger(__name__)
SOURCE = "HISTDATA"
_BATCH = 50_000


@dataclass
class ImportReport:
    path: str = ""
    rows: int = 0            # dosyadaki veri satırı
    imported: int = 0
    duplicates: int = 0      # aynı zaman damgası (ilk satır tutulur)
    out_of_order: int = 0    # öncekinden eski zaman damgası (yine de alınır; sıralı saklanır)
    invalid: list[tuple[int, str]] = field(default_factory=list)   # (satır no, neden) — alınmadı
    first: datetime | None = None
    last: datetime | None = None

    @property
    def clean(self) -> bool:
        return not (self.duplicates or self.out_of_order or self.invalid)

    def summary(self) -> str:
        span = f"{self.first:%Y-%m-%d %H:%M} → {self.last:%Y-%m-%d %H:%M} UTC" if self.first else "-"
        return (f"{self.path}: {self.rows} satır, {self.imported} içe aktarıldı ({span}); "
                f"tekrar={self.duplicates}, sırasız={self.out_of_order}, geçersiz={len(self.invalid)}")


def parse_line(line: str, offset: timezone) -> tuple[datetime, Decimal, Decimal, Decimal, Decimal]:
    parts = line.strip().split(";")
    if len(parts) != 6:
        raise ValueError(f"6 alan beklenir (YYYYMMDD HHMMSS;O;H;L;C;V), {len(parts)} bulundu")
    t = datetime.strptime(parts[0], "%Y%m%d %H%M%S").replace(tzinfo=offset).astimezone(UTC)
    try:
        o, h, l, c = (Decimal(x) for x in parts[1:5])
    except InvalidOperation as e:
        raise ValueError(f"sayı okunamadı: {parts[1:5]}") from e
    return t, o, h, l, c


def iter_m1(path: str | Path, pair: str, pip_size: Decimal, spread_pips: Decimal, utc_offset_hours: int,
            report: ImportReport | None = None) -> Iterator[QuoteCandle]:
    rep = report if report is not None else ImportReport()
    rep.path = str(path)
    off = timezone(timedelta(hours=utc_offset_hours))
    spread = spread_pips * pip_size
    seen_prev: datetime | None = None
    seen: set[datetime] = set()
    with Path(path).open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            rep.rows += 1
            try:
                t, o, h, l, c = parse_line(line, off)
                bid = OHLC(o, h, l, c)
                ask = OHLC(o + spread, h + spread, l + spread, c + spread)
            except (ValueError, TypeError) as e:
                rep.invalid.append((n, str(e)))
                log.warning("histdata satır %d geçersiz, atlandı: %s", n, e)
                continue
            if t in seen:
                rep.duplicates += 1
                log.warning("histdata satır %d: tekrarlı zaman damgası %s, atlandı", n, t.isoformat())
                continue
            if seen_prev is not None and t < seen_prev:
                rep.out_of_order += 1
                log.warning("histdata satır %d: sırasız zaman damgası %s", n, t.isoformat())
            seen.add(t)
            seen_prev = t if seen_prev is None else max(seen_prev, t)
            rep.imported += 1
            rep.first = t if rep.first is None else min(rep.first, t)
            rep.last = t if rep.last is None else max(rep.last, t)
            yield QuoteCandle(pair, Timeframe.M1, t, bid, ask, True, None)


def import_file(path: str | Path, pair: str, pip_size: Decimal, spread_pips: Decimal, utc_offset_hours: int,
                store: CandleStore) -> ImportReport:
    rep = ImportReport()
    batch: list[QuoteCandle] = []
    for c in iter_m1(path, pair, pip_size, spread_pips, utc_offset_hours, rep):
        batch.append(c)
        if len(batch) >= _BATCH:
            store.put_candles(SOURCE, batch)
            batch = []
    if batch:
        store.put_candles(SOURCE, batch)
    log.info(rep.summary())
    return rep
