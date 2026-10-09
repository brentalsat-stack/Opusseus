"""Günlük kayıp sınırı (RK-R003): gün başına en fazla N kayıp → o gün yeni emir yok (DAY_LOCKED, §17).
Gün sınırı config'den (DECISIONS: Europe/Istanbul 00:00). Kayıp = net PnL < 0 olarak kapanan işlem (Q-P3)."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ..data.tz import ensure_utc


class DayLossTracker:
    def __init__(self, tz: ZoneInfo, reset_time: time, max_losses: int):
        if max_losses < 1:
            raise ValueError("max_losses ≥ 1 olmalı")
        self.tz, self.reset, self.max_losses = tz, reset_time, max_losses
        self._losses: Counter[date] = Counter()

    @classmethod
    def from_config(cls, cfg) -> "DayLossTracker":
        cfg.require("risk")
        return cls(ZoneInfo(cfg.get("day_reset.tz")), time.fromisoformat(cfg.get("day_reset.time")),
                   cfg.get("max_losses_per_day"))

    def day_key(self, t: datetime) -> date:
        """İşlem günü kimliği: yerel duvar saatinden reset saati çıkarılarak."""
        local = ensure_utc(t).astimezone(self.tz).replace(tzinfo=None)
        return (local - timedelta(hours=self.reset.hour, minutes=self.reset.minute)).date()

    def record_close(self, close_time: datetime, net_pnl: Decimal) -> bool:
        """Kapanan işlemi kaydet. Kayıpsa (net_pnl < 0) sayaç artar; True döner."""
        if net_pnl < 0:
            self._losses[self.day_key(close_time)] += 1
            return True
        return False

    def losses(self, t: datetime) -> int:
        return self._losses[self.day_key(t)]

    def is_locked(self, t: datetime) -> bool:
        return self.losses(t) >= self.max_losses
