"""Likidite seviyeleri (LQ-R001): minor tepe/dipler (MS-R002), eşit tepe/dipler (≤ eqh_tolerance).

Minor high i : high[i], high[i−1]'i ≥1 pipette aştı ve high[i+1] onu kıramadı. Minor low simetrik.
Eşit tepe/dip: iki minor high arasındaki fark ≤ tolerans (SINIR DAHİL) ve aralarında hiçbir mum max(h1,h2)'nin tolerans üstüne çıkmadı.
Trendline: çizim kuralı kaynakta yok (U-04) → kodlanmadı.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence

from ..data.models import Candle


class Side(str, Enum):
    HIGH = "HIGH"    # alıcı tarafı likidite (tepelerin üstü)
    LOW = "LOW"      # satıcı tarafı likidite (diplerin altı)


class Source(str, Enum):
    SWING = "SWING"
    MINOR = "MINOR"
    EQ = "EQ"


@dataclass(frozen=True)
class Level:
    side: Side
    price: Decimal
    index: int          # seviyenin (EQ'da ikinci tepenin) oluştuğu mum
    source: Source


def minor_highs(c: Sequence[Candle], pipette: Decimal, lo: int = 1, hi: int | None = None) -> list[int]:
    hi = len(c) - 1 if hi is None else hi          # i+1 gerektiği için son mum aday olamaz
    return [i for i in range(max(lo, 1), min(hi, len(c) - 1))
            if c[i].high - c[i - 1].high >= pipette and c[i + 1].high - c[i].high < pipette]


def minor_lows(c: Sequence[Candle], pipette: Decimal, lo: int = 1, hi: int | None = None) -> list[int]:
    hi = len(c) - 1 if hi is None else hi
    return [i for i in range(max(lo, 1), min(hi, len(c) - 1))
            if c[i - 1].low - c[i].low >= pipette and c[i].low - c[i + 1].low < pipette]


def equal_pools(c: Sequence[Candle], idxs: Sequence[int], side: Side, tol: Decimal) -> list[Level]:
    """İki minor uç arasındaki fark ≤ tol (dahil) ve aradaki mumlar havuzu tol'dan fazla aşmıyorsa eşit tepe/dip."""
    out: list[Level] = []
    val = (lambda i: c[i].high) if side is Side.HIGH else (lambda i: -c[i].low)
    for b in range(1, len(idxs)):
        i2 = idxs[b]
        for a in range(b - 1, -1, -1):
            i1 = idxs[a]
            top = max(val(i1), val(i2))
            between = max((val(k) for k in range(i1 + 1, i2)), default=top)
            if between - top > tol:
                break                                   # aralarında havuz aşıldı; daha eskiler de geçersiz
            if abs(val(i1) - val(i2)) <= tol:
                price = top if side is Side.HIGH else -top
                out.append(Level(side, price, i2, Source.EQ))
                break
    return out


def swept(level: Level, c: Candle, pipette: Decimal) -> bool:
    """Mumun wick'i seviyeyi ≥ 1 pipette geçti mi (yönüne bakmadan, kapanış şartı yok)."""
    return c.high - level.price >= pipette if level.side is Side.HIGH else level.price - c.low >= pipette
