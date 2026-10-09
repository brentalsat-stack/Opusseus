"""Seans pencereleri ve rollover yasağı (SS-R001, SS-R002). Saat dilimleri IANA ile dinamik (DST otomatik).
Pencere [başlangıç, bitiş) — bitiş dışlanır (Q-P2: kaynak sınır davranışını vermiyor)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from ..data.tz import ISTANBUL, UTC, ensure_utc, local_to_utc


def _in_window(t: time, start: time, end: time) -> bool:
    return start <= t < end if start < end else (t >= start or t < end)   # gece yarısını aşan pencere


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""        # "" | OUT_OF_SESSION | BLACKOUT
    rule: str = ""


class SessionClock:
    def __init__(self, session_tz: ZoneInfo, windows: list[tuple[time, time]], display_tz: ZoneInfo = ISTANBUL,
                 blackout: Optional[tuple[ZoneInfo, time, time]] = None):
        self.tz, self.windows, self.display_tz, self.blackout = session_tz, windows, display_tz, blackout

    @classmethod
    def from_config(cls, cfg, with_blackout: bool = True) -> "SessionClock":
        cfg.require("session_blackout" if with_blackout else "session")
        wins = [(time.fromisoformat(a), time.fromisoformat(b)) for a, b in cfg.get("sessions_london")]
        bo = None
        if with_blackout:
            bo = (ZoneInfo(cfg.get("blackout.tz")), time.fromisoformat(cfg.get("blackout.start")),
                  time.fromisoformat(cfg.get("blackout.end")))
        return cls(ZoneInfo(cfg.get("timezones.session")), wins, ZoneInfo(cfg.get("timezones.display")), bo)

    def in_session(self, t: datetime) -> bool:
        """SS-R001."""
        local = ensure_utc(t).astimezone(self.tz).time()
        return any(_in_window(local, a, b) for a, b in self.windows)

    def in_blackout(self, t: datetime) -> bool:
        """SS-R002: yasak pencerede (21:00–23:00 UTC) yeni emir yok."""
        if self.blackout is None:
            raise RuntimeError("blackout yapılandırılmadı (session_blackout modülü)")
        tz, a, b = self.blackout
        return _in_window(ensure_utc(t).astimezone(tz).time(), a, b)

    def may_open(self, t: datetime) -> Decision:
        """Yeni emir/sinyal için zaman filtresi (önce yasak pencere, sonra seans)."""
        if self.blackout is not None and self.in_blackout(t):
            return Decision(False, "BLACKOUT", "SS-R002")
        if not self.in_session(t):
            return Decision(False, "OUT_OF_SESSION", "SS-R001")
        return Decision(True)

    def windows_utc(self, day: date) -> list[tuple[datetime, datetime]]:
        """Verilen Londra gününün pencereleri (UTC)."""
        return [(local_to_utc(datetime.combine(day, a), self.tz), local_to_utc(datetime.combine(day, b), self.tz))
                for a, b in self.windows]

    def windows_display(self, day: date) -> list[tuple[datetime, datetime]]:
        """Aynı pencereler gösterim saat diliminde (Europe/Istanbul)."""
        return [(a.astimezone(self.display_tz), b.astimezone(self.display_tz)) for a, b in self.windows_utc(day)]
