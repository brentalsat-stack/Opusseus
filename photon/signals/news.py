"""Haber uyarısı (DECISIONS §6): sinyal ENGELLENMEZ. O gün EUR/USD için yüksek etkili haber varsa o günün TÜM sinyallerine not.
Takvim: ForexFactory (resmi haftalık dışa aktarım JSON'u). "O gün" = `day_reset.tz` günü (Q-P5). Takvimin kapsamadığı gün → UNKNOWN."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from ..data.tz import ISTANBUL, ensure_utc
from ..data.sources.http import HttpGet, default_get, get_with_retry


@dataclass(frozen=True)
class NewsEvent:
    title: str
    currency: str
    time: datetime      # UTC
    impact: str         # High | Medium | Low | Holiday


def parse_forexfactory(raw: bytes | str) -> list[NewsEvent]:
    """ForexFactory haftalık JSON: [{title,country,date(ISO+offset),impact,...}]. Tarihi olmayan/bozuk satır hata verir."""
    out = []
    for r in json.loads(raw):
        t = datetime.fromisoformat(r["date"])
        out.append(NewsEvent(r["title"], r["country"], ensure_utc(t), r["impact"]))
    return out


def fetch_forexfactory(url: str, http_get: HttpGet = default_get, max_retries: int = 3) -> list[NewsEvent]:
    status, body = get_with_retry(url, {"User-Agent": "photon-trade"}, http_get, max_retries)
    if status != 200:
        raise RuntimeError(f"ForexFactory takvimi alınamadı: HTTP {status}")
    return parse_forexfactory(body)


class NewsStatus(str, Enum):
    WARN = "WARN"          # o gün yüksek etkili haber var → sinyallere not
    CLEAR = "CLEAR"
    UNKNOWN = "UNKNOWN"    # takvim o günü kapsamıyor


@dataclass(frozen=True)
class NewsNote:
    status: NewsStatus
    events: tuple[NewsEvent, ...] = ()

    def text(self, display_tz: ZoneInfo = ISTANBUL) -> str:
        if self.status is NewsStatus.WARN:
            items = ", ".join(f"{e.currency} {e.title} ({e.time.astimezone(display_tz):%H:%M})" for e in self.events)
            return f"⚠ Bugün yüksek etkili haber var: {items}"
        if self.status is NewsStatus.UNKNOWN:
            return "ℹ Haber takvimi bu günü kapsamıyor (bilinmiyor)"
        return ""


class NewsCalendar:
    def __init__(self, events: Iterable[NewsEvent], currencies: Iterable[str], impact: str, day_tz: ZoneInfo):
        self.day_tz, self.impact, self.currencies = day_tz, impact.lower(), frozenset(currencies)
        evs = list(events)
        self._days = {self._day(e.time) for e in evs}
        self._cover = (min(self._days), max(self._days)) if self._days else None
        self._hits = [e for e in evs if e.currency in self.currencies and e.impact.lower() == self.impact]

    @classmethod
    def from_config(cls, cfg, events: Iterable[NewsEvent]) -> "NewsCalendar":
        cfg.require("news")
        return cls(events, cfg.get("news_filter.currencies"), cfg.get("news_filter.impact"),
                   ZoneInfo(cfg.get("day_reset.tz")))

    def _day(self, t: datetime) -> date:
        return ensure_utc(t).astimezone(self.day_tz).date()

    def note(self, t: datetime) -> NewsNote:
        d = self._day(t)
        todays = tuple(e for e in self._hits if self._day(e.time) == d)
        if todays:
            return NewsNote(NewsStatus.WARN, todays)
        if self._cover and self._cover[0] <= d <= self._cover[1]:
            return NewsNote(NewsStatus.CLEAR)
        return NewsNote(NewsStatus.UNKNOWN)
