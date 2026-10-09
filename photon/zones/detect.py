"""Zon algılama (saf fonksiyonlar). Kopuş mumu t'de, yalnızca t'ye kadarki kapanmış mumlarla.

SD-R002 pivot (STB/BTS): karşı yönlü mum(lar) + onları yutan kopuş mumu. Yutma = kopuş mumunun KAPANIŞI, mum(lar)ın
  en uç wick'inin ≥ 1 pipette ötesinde (Q-Z1). Koşu = kopuş mumundan geriye ardışık karşı yönlü mumların en uzunu.
SD-R001 range (kullanıcı tanımı, DECISIONS §3): ≥ `min_chain` mumluk inside-bar zinciri (sonraki mumlar ilk mumun
  high–low aralığında); aralıktan KAPANIŞLA çıkış = kopuş. Birden çok geçerli mother varsa kopuşa uğrayan en dıştaki seçilir.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from ..data.models import Candle
from .models import Origin, ZoneKind

MAX_CHAIN_LOOKBACK = 200   # uygulama sınırı (strateji parametresi değil): zincir aramasında geriye en fazla mum


@dataclass(frozen=True)
class Geometry:
    kind: ZoneKind
    origin: Origin
    draw: str
    top: Decimal
    bottom: Decimal
    first_index: int


def pivot_zone(candles: Sequence[Candle], t: int, pipette: Decimal, draw: str) -> Optional[Geometry]:
    """SD-R002. `draw`: RANGE/PIVOT → tüm koşu; CANDLE → koşunun son (kopuşa en yakın) mumu."""
    if draw not in ("RANGE", "PIVOT", "CANDLE"):
        raise NotImplementedError(f"çizim modu {draw} kodlanmadı (FRACTAL_WICK: Q-Z2)")
    b = candles[t]
    if b.close > b.open:                      # bullish kopuş → STB → talep
        kind, s = ZoneKind.DEMAND, 1
    elif b.close < b.open:
        kind, s = ZoneKind.SUPPLY, -1
    else:
        return None
    run: list[int] = []
    ext = None                                # koşunun karşı uç wick'i (talepte en yüksek high)
    for j in range(t - 1, -1, -1):
        c = candles[j]
        if s * (c.close - c.open) >= 0:       # karşı yönlü (bearish) değil
            break
        e = c.high if s > 0 else -c.low
        cand = e if ext is None else max(ext, e)
        if s * b.close - cand < pipette:      # kopuş mumu bunu yutmuyor
            break
        ext = cand
        run.append(j)
    if not run:
        return None
    run.reverse()
    if draw == "CANDLE":
        use = [run[-1]]
    else:
        use = run
    return Geometry(kind, Origin.PIVOT, "CANDLE" if draw == "CANDLE" else "RANGE",
                    max(candles[j].high for j in use), min(candles[j].low for j in use), use[0])


def range_zone(candles: Sequence[Candle], t: int, pipette: Decimal, min_chain: int) -> Optional[Geometry]:
    """SD-R001 (kullanıcı tanımı): t kopuş mumu; zincir = mother + ≥(min_chain−1) inside bar."""
    c = candles[t]
    mx = None            # m+1..t-1 arası en yüksek high
    mn = None
    best: Optional[int] = None
    for m in range(t - 1, max(-1, t - 1 - MAX_CHAIN_LOOKBACK), -1):
        if t - 1 - m >= min_chain - 1:
            hm, lm = candles[m].high, candles[m].low
            inside = mx - hm < pipette and lm - mn < pipette
            if inside and (c.close - hm >= pipette or lm - c.close >= pipette):
                best = m                       # daha dış (daha eski) geçerli mother kopuşa uğruyorsa onu tercih et
        h, l = candles[m].high, candles[m].low
        mx = h if mx is None else max(mx, h)
        mn = l if mn is None else min(mn, l)
    if best is None:
        return None
    chain = range(best, t)
    top, bottom = max(candles[k].high for k in chain), min(candles[k].low for k in chain)
    kind = ZoneKind.DEMAND if c.close - candles[best].high >= pipette else ZoneKind.SUPPLY
    return Geometry(kind, Origin.RANGE, "RANGE", top, bottom, best)
