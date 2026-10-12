"""HistData.com içe aktarıcı: EURUSD M1 **bid** (ASCII). Dosya kaynaklı veri (ağ yok).

Format (başlıksız, ayraç ';'): `YYYYMMDD HHMMSS;Open;High;Low;Close;Volume` — hacim 0 (yok sayılır).
Saat: sabit EST = UTC−5, DST YOK (DECISIONS §7) → önce UTC'ye çevrilir; NY 17:00 mum sınırları sonra zoneinfo ile hesaplanır.
Veri yalnız bid: ask = bid + sabit spread (costs.spread_pips = 0.4, kullanıcı kararı).
Hatalı/tekrarlı/sırasız satırlar sessizce düzeltilmez: sayılır, loglanır ve raporda gösterilir.
"""
from __future__ import annotations

import glob
import logging
import re
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
    overwritten: int = 0     # önbellekte zaten bulunan zaman damgası (yeniden içe aktarma / dosyalar arası çakışma)
    changed: int = 0         # overwritten içinde değeri (bid OHLC) FARKLI olanlar

    @property
    def clean(self) -> bool:
        return not (self.duplicates or self.out_of_order or self.invalid or self.changed)

    def summary(self) -> str:
        span = f"{self.first:%Y-%m-%d %H:%M} → {self.last:%Y-%m-%d %H:%M} UTC" if self.first else "-"
        return (f"{self.path}: {self.rows} satır, {self.imported} içe aktarıldı ({span}); "
                f"tekrar={self.duplicates}, sırasız={self.out_of_order}, geçersiz={len(self.invalid)}"
                + (f", önbellekte zaten vardı={self.overwritten} (değeri farklı={self.changed})" if self.overwritten else ""))


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


def _flush(store: CandleStore, batch: list[QuoteCandle], rep: ImportReport) -> None:
    """Yazmadan önce aynı zaman damgasının önbellekte olup olmadığını denetler (sessiz üzerine yazma yok: sayılır)."""
    lo, hi = min(c.open_time for c in batch), max(c.open_time for c in batch)
    have = {c.open_time: c for c in store.get_candles(SOURCE, batch[0].pair, Timeframe.M1, lo, hi + timedelta(minutes=1))}
    for c in batch:
        old = have.get(c.open_time)
        if old is not None:
            rep.overwritten += 1
            if old.bid != c.bid:
                rep.changed += 1
    store.put_candles(SOURCE, batch)


def import_file(path: str | Path, pair: str, pip_size: Decimal, spread_pips: Decimal, utc_offset_hours: int,
                store: CandleStore) -> ImportReport:
    rep = ImportReport()
    batch: list[QuoteCandle] = []
    for c in iter_m1(path, pair, pip_size, spread_pips, utc_offset_hours, rep):
        batch.append(c)
        if len(batch) >= _BATCH:
            _flush(store, batch, rep)
            batch = []
    if batch:
        _flush(store, batch, rep)
    log.info(rep.summary())
    return rep


# ---------------------------------------------------------------- çok yıllı içe aktarma
_YEAR = re.compile(r"_M1_(\d{4})", re.I)
MAX_BOUNDARY_GAP = timedelta(days=4)     # yıl sınırı: hafta sonu + yılbaşı tatili normal; daha uzun boşluk SORUN olarak işaretlenir


def file_year(path: str | Path) -> int | None:
    m = _YEAR.search(Path(path).name)
    return int(m.group(1)) if m else None


def resolve_paths(spec: str | Path, pair: str | None = None, years: tuple[int, int] | None = None) -> list[Path]:
    """Dosya, dizin veya glob → yıla göre sıralı dosya listesi. Dizinde `DAT_ASCII_<PAIR>_M1_<YYYY>.csv` desenli dosyalar alınır."""
    spec = str(spec)
    if any(ch in spec for ch in "*?["):
        paths = [Path(p) for p in sorted(glob.glob(spec))]
    elif Path(spec).is_dir():
        pat = f"DAT_ASCII_{pair}_M1_*.csv" if pair else "DAT_ASCII_*_M1_*.csv"
        paths = sorted(Path(spec).glob(pat))
    else:
        paths = [Path(spec)]
    if years is not None:
        paths = [p for p in paths if (y := file_year(p)) is not None and years[0] <= y <= years[1]]
    return sorted(paths, key=lambda p: (file_year(p) or 0, p.name))


@dataclass
class Boundary:
    prev: str
    nxt: str
    prev_last: datetime
    next_first: datetime
    gap: timedelta
    status: str          # OK | ÇAKIŞMA | UZUN_BOŞLUK

    def line(self) -> str:
        return (f"  sınır {self.prev} → {self.nxt}: son {self.prev_last:%Y-%m-%d %H:%M} / ilk {self.next_first:%Y-%m-%d %H:%M} UTC, "
                f"boşluk {self.gap}  [{self.status}]")


@dataclass
class MultiReport:
    reports: list[ImportReport] = field(default_factory=list)
    boundaries: list[Boundary] = field(default_factory=list)
    missing_years: list[int] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return sum(r.rows for r in self.reports)

    @property
    def imported(self) -> int:
        return sum(r.imported for r in self.reports)

    @property
    def invalid(self) -> list[tuple[int, str]]:
        return [x for r in self.reports for x in r.invalid]

    @property
    def clean(self) -> bool:
        return all(r.clean for r in self.reports) and all(b.status == "OK" for b in self.boundaries) and not self.missing_years

    def summary(self) -> str:
        L = [r.summary() for r in self.reports]
        L += [b.line() for b in self.boundaries]
        if self.missing_years:
            L.append(f"  EKSİK YIL(LAR): {self.missing_years}")
        first = min((r.first for r in self.reports if r.first), default=None)
        last = max((r.last for r in self.reports if r.last), default=None)
        L.append(f"TOPLAM: {len(self.reports)} dosya, {self.rows} satır, {self.imported} içe aktarıldı"
                 + (f" ({first:%Y-%m-%d} → {last:%Y-%m-%d} UTC)" if first else "")
                 + f"; tekrar={sum(r.duplicates for r in self.reports)}, sırasız={sum(r.out_of_order for r in self.reports)}, "
                   f"geçersiz={len(self.invalid)}, önbellekte zaten vardı={sum(r.overwritten for r in self.reports)} "
                   f"(farklı={sum(r.changed for r in self.reports)})")
        return "\n".join(L)


def import_many(paths: list[Path], pair: str, pip_size: Decimal, spread_pips: Decimal, utc_offset_hours: int,
                store: CandleStore) -> MultiReport:
    """Yıllık dosyaları sırayla tek önbelleğe birleştirir. Yıl sınırlarında süreklilik (çakışma / >4 gün boşluk) ve eksik yıl raporlanır;
    hiçbir şey sessizce düzeltilmez. Dosya adındaki yıl dizisinde atlama varsa EKSİK YIL yazılır."""
    mr = MultiReport()
    for p in paths:
        rep = import_file(p, pair, pip_size, spread_pips, utc_offset_hours, store)
        if mr.reports and rep.first is not None and mr.reports[-1].last is not None:
            prev = mr.reports[-1]
            gap = rep.first - prev.last
            status = "ÇAKIŞMA" if rep.first <= prev.last else ("UZUN_BOŞLUK" if gap > MAX_BOUNDARY_GAP else "OK")
            mr.boundaries.append(Boundary(Path(prev.path).name, p.name, prev.last, rep.first, gap, status))
        mr.reports.append(rep)
    ys = [y for y in (file_year(p) for p in paths) if y is not None]
    if ys:
        mr.missing_years = [y for y in range(min(ys), max(ys) + 1) if y not in ys]
    return mr
