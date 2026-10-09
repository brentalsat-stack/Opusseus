"""Premium / Discount (PD-R001, FM-08). PD-R003 (range filtresi) Aşama 4'te.

Q-S06 (AMBIGUOUS: swing mi internal mi?) — uygulanan: TF'nin ONAYLI swing aralığı [swing_low, swing_high].
Onaysız uçta aralık değişebileceğinden P/D bilinmez (None). Internal aralık üretilmez.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from .models import MarketState, Trend


class PD(str, Enum):
    DISCOUNT = "DISCOUNT"
    PREMIUM = "PREMIUM"
    EQ = "EQ"            # tam EQ üzerinde: ne premium ne discount


def eq(low: Decimal, high: Decimal) -> Decimal:
    """FM-08 / PD-R001: EQ = low + 0.5 × (high − low)."""
    if high <= low:
        raise ValueError("high > low olmalı")
    return low + (high - low) / 2


def classify(price: Decimal, low: Decimal, high: Decimal) -> PD:
    """PD-R001: price < EQ → discount; price > EQ → premium."""
    e = eq(low, high)
    return PD.DISCOUNT if price < e else PD.PREMIUM if price > e else PD.EQ


def swing_range(state: MarketState) -> Optional[tuple[Decimal, Decimal]]:
    """Onaylı swing aralığı (low, high); yoksa None (Q-S06)."""
    if state.swing_trend is Trend.UNDEFINED or state.swing_high is None or state.swing_low is None:
        return None
    if not (state.swing_high.confirmed and state.swing_low.confirmed):
        return None
    return state.swing_low.price, state.swing_high.price


def classify_state(state: MarketState, price: Decimal) -> Optional[PD]:
    r = swing_range(state)
    return None if r is None else classify(price, *r)


def aligned(direction: Trend, pd: Optional[PD]) -> Optional[bool]:
    """Long ↔ discount, short ↔ premium (POI puan kriteri #9 girdisi). Bilinmiyorsa/EQ'daysa None/False."""
    if pd is None:
        return None
    return pd is (PD.DISCOUNT if direction is Trend.BULL else PD.PREMIUM)


# ---- PD-R003: range ortası filtresi (DECISIONS §3, ZORUNLU kapı) ----
def position_pct(price: Decimal, low: Decimal, high: Decimal) -> Decimal:
    """Fiyatın range içindeki yeri, % (0 = low, 100 = high); range dışında <0 / >100 olabilir."""
    if high <= low:
        raise ValueError("high > low olmalı")
    return (price - low) / (high - low) * 100


@dataclass(frozen=True)
class RangeFilterResult:
    passed: bool
    reason: str                       # "" | RANGE_UNKNOWN | MIDDLE_OF_RANGE | WRONG_SIDE_OF_RANGE
    position_pct: Optional[Decimal]


def range_filter(direction: Trend, zone_eq: Decimal, state: MarketState, band_pct: Decimal) -> RangeFilterResult:
    """PD-R003: long yalnız range'in alt %band'ında, short yalnız üst %band'ında. Uygulanan range: `state` (M15 swing range
    varsayılan, Q-Z9); ölçülen nokta: zonun EQ'su. Range bilinmiyorsa kapı KAPALI (fail-closed)."""
    r = swing_range(state)
    if r is None:
        return RangeFilterResult(False, "RANGE_UNKNOWN", None)
    pct = position_pct(zone_eq, *r)
    ok = pct <= band_pct if direction is Trend.BULL else pct >= 100 - band_pct
    return RangeFilterResult(ok, "" if ok else "MIDDLE_OF_RANGE" if band_pct <= pct <= 100 - band_pct
                             else "WRONG_SIDE_OF_RANGE", pct)

