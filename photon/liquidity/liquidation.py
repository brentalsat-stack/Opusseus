"""Liquidation (EN-R001 adım 1, ZORUNLU kapı) ve V-shape çıkış ölçütü (Q-Z8 önerisi).

Liquidation: POI'ye (zona) girerken, execution TF'de (M1) bir minor tepe/dip veya eşit tepe/dip wick ile süpürüldü.
  * Mevcut dokunuş (mitigation) = `upto`'ya kadarki en son 'zonun tamamen dışında' mumdan sonraki ilk mum.
  * Seviye penceresi: fiyatın zonu SON terk ettiği andan (önceki ziyaretin sonu; ziyaret yoksa zonun doğduğu an) bu dokunuşa kadar.
  * Seviye: pencerede oluşmuş, zonun dışında (talepte zon.top üstünde) minor dip/tepe ya da eşit dip/tepe; seviyeyi ≥1 pipette
    geçen İLK mum (wick, kapanış şartı yok) dokunuş mumundan sonra olamaz.
Uyarı (Q-L1): zonun dışındaki seviye dokunuştan önce oluştuysa, zona inen fiyat onu zaten geçer; yani tek-minor seviyeler kapıyı
  neredeyse her zaman geçirir. `LiquidationResult.level.source` ile EQ (eşit tepe/dip) ve MINOR ayrılır; politika katmanı seçer.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from ..data.models import Candle
from ..zones.models import Zone, ZoneKind
from .levels import Level, Side, Source, equal_pools, minor_highs, minor_lows, swept


@dataclass(frozen=True)
class LiquidationResult:
    found: bool
    reason: str = ""                 # found=False ise: NOT_MITIGATED | NO_SWEEP
    level: Optional[Level] = None
    sweep_index: Optional[int] = None
    window_start: Optional[int] = None
    touch_index: Optional[int] = None


def liquidation(m1: Sequence[Candle], zone: Zone, upto: int, tol: Decimal, pipette: Decimal) -> LiquidationResult:
    """`m1[:upto+1]` mumları kullanılır (upto dahil). `tol`: eşit tepe/dip toleransı (fiyat)."""
    demand = zone.kind is ZoneKind.DEMAND
    outside = (lambda c: c.low > zone.top) if demand else (lambda c: c.high < zone.bottom)
    a = next((i for i in range(upto, -1, -1) if outside(m1[i])), None)       # zonun tamamen dışındaki son mum
    touch = (a + 1) if a is not None else 0
    if touch > upto or not (m1[touch].low <= zone.top and m1[touch].high >= zone.bottom):
        # a'dan sonraki ilk mum zonu kesmiyorsa (veri boşluğu/zon aşıldı) ilk kesişen mumu ara
        touch = next((i for i in range(touch, upto + 1)
                      if m1[i].low <= zone.top and m1[i].high >= zone.bottom), None)
    if touch is None:
        return LiquidationResult(False, "NOT_MITIGATED")
    # pencere başı: bu ziyaretten önceki en son 'zonu kesen/aşan' mumdan sonrası; yoksa zonun doğduğu an
    prev_visit = next((i for i in range(touch - 1, -1, -1) if not outside(m1[i])), None)
    born = next((i for i, c in enumerate(m1) if c.open_time >= zone.created_time), 0)
    start = max(born, (prev_visit + 1) if prev_visit is not None else 0)
    side = Side.LOW if demand else Side.HIGH
    idx = (minor_lows if demand else minor_highs)(m1, pipette, start, touch)
    levels = [Level(side, m1[i].low if demand else m1[i].high, i, Source.MINOR) for i in idx]
    levels += equal_pools(m1, idx, side, tol)
    levels = [lv for lv in levels if (lv.price > zone.top if demand else lv.price < zone.bottom)]
    levels.sort(key=lambda lv: (lv.source is not Source.EQ, lv.index))      # EQ öncelikli, sonra zaman
    for lv in levels:
        j = next((k for k in range(lv.index + 1, touch + 1) if swept(lv, m1[k], pipette)), None)
        if j is not None:
            return LiquidationResult(True, "", lv, j, start, touch)
    return LiquidationResult(False, "NO_SWEEP", window_start=start, touch_index=touch)


def v_shape_exit(touch_index: int, choch_index: int, max_candles: int) -> bool:
    """V-shape (agresif tepki) ölçüt ÖNERİSİ (Q-Z8): POI'ye dokunuştan M1 CHoCH'a kadar geçen M1 mum sayısı ≤ max_candles."""
    if choch_index < touch_index:
        raise ValueError("CHoCH dokunuştan önce olamaz")
    return choch_index - touch_index <= max_candles
