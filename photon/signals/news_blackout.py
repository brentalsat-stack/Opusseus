"""V8b haber filtresi (T-M15BT [00:25:48, 01:03:01, 01:45:57]): yüksek etkili haberde (NFP, CPI, FOMC, ECB, Retail Sales) emir bırakma /
pozisyon taşıma yok. Geçmiş takvim yok (Q-P5) → kullanıcının sağladığı CSV: sütunlar `date` (YYYY-MM-DD), `time_utc` (HH:MM), `event`
(Türkçe başlıklar da kabul: tarih, saat, olay; ya da tek `datetime_utc`). Olay ±`window_min` dk içinde: yeni emir yok, dolum yok,
bekleyen emir iptal, açık pozisyon pencere başında piyasadan kapanır (backtest motoru)."""
from __future__ import annotations

import bisect
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
_ALIASES = {"date": ("date", "tarih"), "time": ("time_utc", "saat", "time", "saat_utc"), "event": ("event", "olay", "title"),
            "dt": ("datetime_utc", "datetime")}


def _col(row: dict, key: str):
    for k in _ALIASES[key]:
        if k in row and row[k] not in (None, ""):
            return row[k].strip()
    return None


@dataclass(frozen=True)
class NewsEvent:
    time: datetime
    name: str


class NewsBlackout:
    def __init__(self, events: list[NewsEvent], window_min: int):
        if window_min < 0:
            raise ValueError("window_min ≥ 0 olmalı")
        self.events = sorted(events, key=lambda e: e.time)
        self.window = timedelta(minutes=window_min)
        self._times = [e.time for e in self.events]

    @classmethod
    def from_csv(cls, path: str | Path, window_min: int = 30) -> "NewsBlackout":
        ev: list[NewsEvent] = []
        with open(path, newline="", encoding="utf-8-sig") as fh:
            lines = [l for l in fh if l.strip() and not l.lstrip().startswith("#")]      # '#' ile başlayan satırlar yorum
            for n, row in enumerate(csv.DictReader(lines), 2):
                row = {(k or "").strip().lower(): v for k, v in row.items()}
                dt = _col(row, "dt")
                try:
                    t = (datetime.fromisoformat(dt.replace("Z", "+00:00")) if dt else
                         datetime.fromisoformat(f"{_col(row, 'date')}T{_col(row, 'time')}"))
                except (TypeError, ValueError):
                    raise ValueError(f"{path}:{n}: tarih/saat okunamadı: {row}") from None
                t = t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
                ev.append(NewsEvent(t, _col(row, "event") or ""))
        if not ev:
            raise ValueError(f"{path}: haber dosyası boş")
        return cls(ev, window_min)

    @classmethod
    def from_config(cls, cfg) -> "NewsBlackout | None":
        nb = cfg.get("news_blackout")
        if not nb:
            return None
        return cls.from_csv(nb["file"], int(nb.get("window_min", 30)))

    def event_in_window(self, t: datetime) -> NewsEvent | None:
        """`t`, bir olayın [olay−w, olay+w) penceresindeyse o olay (pencere genişlikleri eşit → olay zamanı (t−w, t+w] aralığında)."""
        i = bisect.bisect_right(self._times, t + self.window) - 1
        return self.events[i] if i >= 0 and self._times[i] > t - self.window else None

    def in_window(self, t: datetime) -> bool:
        return self.event_in_window(t) is not None
