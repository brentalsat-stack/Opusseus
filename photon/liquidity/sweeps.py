"""Sweep zone (LQ-R002) ve inducement (LQ-R003). Her ikisi POI PUAN kriteridir (zorunlu değil, DECISIONS §3)."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from ..data.models import Candle
from ..structure.models import Kind, SwingPoint
from ..zones.models import Zone, ZoneKind
from .levels import Level, Side, Source, equal_pools, minor_highs, minor_lows, swept


def _unswept_before(level: Level, c: Sequence[Candle], upto: int, pipette: Decimal) -> bool:
    return not any(swept(level, c[k], pipette) for k in range(level.index + 1, upto))


def range_liquidity(c: Sequence[Candle], swing_log: Sequence[SwingPoint], side: Side, upto: int,
                    tol: Decimal, pipette: Decimal) -> list[Level]:
    """`upto` anında bilinen, henüz süpürülmemiş likidite (yalnızca `upto` öncesi mumlar): TF'nin son onaylı swing
    ucu (taraf için) + son karşı swing'den bu yana oluşan eşit tepe/dipler. Q-Z6 (kaynakta 'hangi likidite' sınırı yok)."""
    want, other = (Kind.HIGH, Kind.LOW) if side is Side.HIGH else (Kind.LOW, Kind.HIGH)
    before = [p for p in swing_log if p.index < upto]
    mine = [p for p in before if p.kind is want]
    opp = [p for p in before if p.kind is other]
    levels: list[Level] = []
    if mine:
        p = mine[-1]
        levels.append(Level(side, p.price, p.index, Source.SWING))
    start = opp[-1].index if opp else 0
    minors = (minor_highs if side is Side.HIGH else minor_lows)(c, pipette, start, upto - 1)
    levels += equal_pools(c, minors, side, tol)
    return [lv for lv in levels if _unswept_before(lv, c, upto, pipette)]


def is_sweep_zone(zone: Zone, c: Sequence[Candle], swing_log: Sequence[SwingPoint], tol: Decimal,
                  pipette: Decimal) -> bool:
    """LQ-R002: zon OLUŞURKEN (first_index..created_index) bir likidite wick'le geçildi ve kopuş mumu geri kapandı.
    Talep: satıcı tarafı (dip) likidite süpürülür, kopuş mumu seviyenin üstünde kapanır; arz simetrik."""
    side = Side.LOW if zone.kind is ZoneKind.DEMAND else Side.HIGH
    for lv in range_liquidity(c, swing_log, side, zone.first_index, tol, pipette):
        pierced = any(swept(lv, c[k], pipette) for k in range(zone.first_index, zone.created_index + 1))
        back = (c[zone.created_index].close > lv.price) if side is Side.LOW else (c[zone.created_index].close < lv.price)
        if pierced and back:
            return True
    return False


def has_inducement(zone: Zone, c: Sequence[Candle], upto: int, tol: Decimal, pipette: Decimal) -> bool:
    """LQ-R003: zonun ÖNÜNDE (fiyat tarafında) süpürülmemiş likidite: talepte zon üstünde, zon yaratıldıktan sonra oluşan
    minor dip veya eşit dipler (arzda simetrik). 'Hemen önünde' mesafe sınırı kaynakta yok (Q-Z7) → sınırsız.
    ALARM anında (fiyat henüz zonun dışındayken) değerlendirilir; `upto` = o anki mum sayısı."""
    lo = zone.created_index + 1
    if zone.kind is ZoneKind.DEMAND:
        idx, side = minor_lows(c, pipette, lo, upto - 1), Side.LOW
        past = lambda p: p - zone.top >= pipette            # zonun üstünde
    else:
        idx, side = minor_highs(c, pipette, lo, upto - 1), Side.HIGH
        past = lambda p: zone.bottom - p >= pipette
    levels = [Level(side, c[i].low if side is Side.LOW else c[i].high, i, Source.MINOR) for i in idx]
    levels += equal_pools(c, idx, side, tol)
    return any(past(lv.price) and _unswept_before(lv, c, upto, pipette) for lv in levels)
