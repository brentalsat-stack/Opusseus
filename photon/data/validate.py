"""Veri doğrulama (FINAL_SPEC §19, T-DATA-01): raporlar, ASLA sessizce düzeltmez/doldurmaz.

Hafta sonu etiketi yalnızca raporlama içindir: Cuma (UTC) başlayıp Pazar/Pazartesi (UTC) biten ve
tüm bir UTC Cumartesi'sini kapsayan boşluk WEEKEND_GAP, diğer her boşluk MISSING'dir.
H4/D1 sabit adımlı olmadığından bu TF'lerde yalnızca tekrar/sıra denetlenir.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable

from .models import QuoteCandle, Timeframe
from .resample import _FIXED

log = logging.getLogger(__name__)


class IssueKind(str, Enum):
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    MISSING = "MISSING"
    WEEKEND_GAP = "WEEKEND_GAP"


@dataclass(frozen=True)
class Issue:
    kind: IssueKind
    start: datetime          # ilgili anın / boşluğun başı (UTC)
    end: datetime | None = None   # boşluklarda ilk gelen sonraki mumun zamanı
    missing_candles: int = 0


@dataclass
class SeriesReport:
    tf: Timeframe
    n_candles: int = 0
    issues: list[Issue] = field(default_factory=list)

    def count(self, kind: IssueKind) -> int:
        return sum(1 for i in self.issues if i.kind is kind)

    @property
    def blocking(self) -> list[Issue]:
        """Düzeltilmeden güvenle kullanılamayacak bulgular (hafta sonu hariç)."""
        return [i for i in self.issues if i.kind is not IssueKind.WEEKEND_GAP]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def summary(self) -> str:
        parts = ", ".join(f"{k.value}={self.count(k)}" for k in IssueKind)
        return f"{self.tf.value}: {self.n_candles} mum; {parts}"

    def format(self, top: int = 15) -> str:
        """İnsan okunur boşluk raporu: tür sayıları, toplam eksik mum, en büyük eksik boşluklar, hafta sonu boşluk sayısı."""
        lines = [self.summary()]
        miss = [i for i in self.issues if i.kind is IssueKind.MISSING]
        lines.append(f"  MISSING boşluk: {len(miss)}, toplam eksik mum: {sum(i.missing_candles for i in miss)}")
        wk = [i for i in self.issues if i.kind is IssueKind.WEEKEND_GAP]
        lines.append(f"  WEEKEND_GAP: {len(wk)} (engelleyici değil)")
        for i in sorted(miss, key=lambda x: -x.missing_candles)[:top]:
            lines.append(f"    MISSING {i.start:%Y-%m-%d %H:%M} → {i.end:%Y-%m-%d %H:%M} UTC  ({i.missing_candles} mum)")
        for i in [x for x in self.issues if x.kind in (IssueKind.DUPLICATE, IssueKind.OUT_OF_ORDER)][:top]:
            lines.append(f"    {i.kind.value} {i.start:%Y-%m-%d %H:%M} UTC")
        return "\n".join(lines)

    def log(self) -> None:
        (log.info if self.ok else log.warning)(self.summary())
        for i in self.blocking:
            log.warning("%s %s%s (eksik mum: %d)", i.kind.value, i.start.isoformat(),
                        f" → {i.end.isoformat()}" if i.end else "", i.missing_candles)


def _is_weekend_gap(start: datetime, end: datetime) -> bool:
    first_sat = (start + timedelta(days=(5 - start.weekday()) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (start.weekday() == 4 and end.weekday() in (6, 0)
            and start <= first_sat and end >= first_sat + timedelta(days=1))


def check_series(candles: Iterable[QuoteCandle], tf: Timeframe) -> SeriesReport:
    rep = SeriesReport(tf)
    fixed = tf in _FIXED
    prev: datetime | None = None  # şimdiye kadarki en büyük zaman
    for c in candles:
        rep.n_candles += 1
        if c.tf is not tf:
            raise ValueError(f"beklenen TF {tf.value}, gelen {c.tf.value}")
        t = c.open_time
        if prev is not None:
            if t == prev:
                rep.issues.append(Issue(IssueKind.DUPLICATE, t))
                continue
            if t < prev:
                rep.issues.append(Issue(IssueKind.OUT_OF_ORDER, t))
                continue
            if fixed:
                gap = t - prev - tf.delta
                if gap > timedelta(0):
                    start = prev + tf.delta
                    kind = IssueKind.WEEKEND_GAP if _is_weekend_gap(start, t) else IssueKind.MISSING
                    rep.issues.append(Issue(kind, start, t, int(gap / tf.delta)))
        prev = t
    return rep
