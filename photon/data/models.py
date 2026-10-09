"""Veri yapıları (FINAL_SPEC §24): Candle. Fiyat = Decimal, zaman = UTC."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

from .tz import UTC


class Timeframe(str, Enum):
    D1 = "D1"
    H4 = "H4"
    M15 = "M15"
    M5 = "M5"  # yalnızca T-EN-01 (M5 POI geçersiz) için temsil edilebilirlik
    M1 = "M1"

    @property
    def delta(self) -> timedelta:
        return {"D1": timedelta(days=1), "H4": timedelta(hours=4), "M15": timedelta(minutes=15),
                "M5": timedelta(minutes=5), "M1": timedelta(minutes=1)}[self.value]


@dataclass(frozen=True)
class Candle:
    pair: str
    tf: Timeframe
    open_time: datetime  # UTC
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    complete: bool = True

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None or self.open_time.utcoffset() != timedelta(0):
            raise ValueError("Candle.open_time UTC (tz-aware) olmalı")
        object.__setattr__(self, "open_time", self.open_time.astimezone(UTC))
        for name in ("open", "high", "low", "close"):
            v = getattr(self, name)
            if not isinstance(v, Decimal):
                raise TypeError(f"Candle.{name} Decimal olmalı (float yasak), alındı: {type(v).__name__}")
            if not v.is_finite() or v <= 0:
                raise ValueError(f"Candle.{name} > 0 olmalı")
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close):
            raise ValueError("OHLC tutarsız (high/low aralığı)")


class PriceSide(str, Enum):
    """Yapı motoruna hangi fiyatın verileceği config'den gelir (candle_price_side)."""
    BID = "BID"
    ASK = "ASK"


def _dec(name: str, v: object) -> Decimal:
    if not isinstance(v, Decimal):
        raise TypeError(f"{name} Decimal olmalı (float yasak), alındı: {type(v).__name__}")
    if not v.is_finite() or v <= 0:
        raise ValueError(f"{name} > 0 olmalı")
    return v


def _utc(name: str, t: datetime) -> datetime:
    if t.tzinfo is None or t.utcoffset() != timedelta(0):
        raise ValueError(f"{name} UTC (tz-aware) olmalı")
    return t.astimezone(UTC)


@dataclass(frozen=True)
class Tick:
    pair: str
    time: datetime  # UTC
    bid: Decimal
    ask: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "time", _utc("Tick.time", self.time))
        _dec("Tick.bid", self.bid)
        _dec("Tick.ask", self.ask)


@dataclass(frozen=True)
class OHLC:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        for n in ("open", "high", "low", "close"):
            _dec(f"OHLC.{n}", getattr(self, n))
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close):
            raise ValueError("OHLC tutarsız (high/low aralığı)")


@dataclass(frozen=True)
class QuoteCandle:
    """Bid ve ask OHLC birlikte tutulur (spread/maliyet için, FINAL_SPEC §22)."""
    pair: str
    tf: Timeframe
    open_time: datetime  # UTC
    bid: OHLC
    ask: OHLC
    complete: bool = True
    n_ticks: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_time", _utc("QuoteCandle.open_time", self.open_time))

    def to_candle(self, side: PriceSide) -> Candle:
        """Yapı motoru için tek-fiyatlı mum (bid veya ask; mid üretilmez — yaklaşık olurdu)."""
        o = self.bid if PriceSide(side) is PriceSide.BID else self.ask
        return Candle(self.pair, self.tf, self.open_time, o.open, o.high, o.low, o.close, self.complete)
