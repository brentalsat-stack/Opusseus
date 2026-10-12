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

MAX_CHAIN_LOOKBACK = 60    # uygulama sınırı (strateji parametresi değil): inside-bar zincir aramasında geriye en fazla mum


@dataclass(frozen=True)
class Geometry:
    kind: ZoneKind
    origin: Origin
    draw: str
    top: Decimal
    bottom: Decimal
    first_index: int
    swept: bool = False      # range_inside_rule=CLOSE: zincirde fitil mother aralığının ötesine (kopuşun TERS yönünde) taştı → sweep zone (LQ-R002)


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


def range_zone(candles: Sequence[Candle], t: int, pipette: Decimal, min_chain: int,
               stats: Optional[dict] = None, inside_rule: str = "WICK") -> Optional[Geometry]:
    """SD-R001 (kullanıcı tanımı): t kopuş mumu; zincir = mother + ≥(min_chain−1) inside bar.
    `inside_rule` (config `range_inside_rule`, kullanıcı kararı): WICK (varsayılan) = zincir mumlarının HIGH–LOW'u mother'ın high–low'u içinde;
    CLOSE = yalnız KAPANIŞLAR mother'ın high–low'u içinde (fitil dışarı taşabilir = sweep); zon sınırı zincirdeki en uç fitile genişler.
    Çıkış (kopuş) her iki kuralda yalnız kapanışla."""
    if inside_rule not in ("WICK", "CLOSE"):
        raise ValueError(f"bilinmeyen range_inside_rule {inside_rule!r}")
    c = candles[t]
    mx = None            # m+1..t-1 arası en yüksek high (CLOSE kuralında en yüksek KAPANIŞ)
    mn = None
    best: Optional[int] = None
    stop = max(-1, t - 1 - MAX_CHAIN_LOOKBACK)
    for m in range(t - 1, stop, -1):
        if t - 1 - m >= min_chain - 1:
            hm, lm = candles[m].high, candles[m].low
            inside = mx - hm < pipette and lm - mn < pipette
            if inside and (c.close - hm >= pipette or lm - c.close >= pipette):
                best = m                       # daha dış (daha eski) geçerli mother kopuşa uğruyorsa onu tercih et
        if inside_rule == "CLOSE":
            h = l = candles[m].close
        else:
            h, l = candles[m].high, candles[m].low
        mx = h if mx is None else max(mx, h)
        mn = l if mn is None else min(mn, l)
    if stats is not None and stop > -1 and best == stop + 1:
        stats["range_lookback_exhausted"] += 1       # en eski aday lookback sınırında: daha eski bir mother olabilirdi (Q-L3)
    if best is None:
        return None
    chain = range(best, t)
    top, bottom = max(candles[k].high for k in chain), min(candles[k].low for k in chain)
    kind = ZoneKind.DEMAND if c.close - candles[best].high >= pipette else ZoneKind.SUPPLY
    swept = False
    if inside_rule == "CLOSE":                 # sweep: kopuşun TERS yönünde mother aralığının ötesine fitil (talepte alt, arzda üst)
        later = [candles[k] for k in range(best + 1, t)]
        swept = (any(candles[best].low - x.low >= pipette for x in later) if kind is ZoneKind.DEMAND
                 else any(x.high - candles[best].high >= pipette for x in later))
    return Geometry(kind, Origin.RANGE, "RANGE", top, bottom, best, swept)
