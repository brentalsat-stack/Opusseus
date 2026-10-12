"""İç içe zon (POI puanı #3) ve rafine M15 zon (D-02, SD-R004): yalnızca geometri; kararı strateji verir."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .models import Zone


def contained_in(inner: Zone, outer: Zone, pipette: Decimal) -> bool:
    """`inner` aynı yönlü `outer`'ın içinde (1 pipette toleransla)."""
    return (inner.kind is outer.kind and inner.bottom >= outer.bottom - pipette and inner.top <= outer.top + pipette)


def nested_parents(z: Zone, parents: Iterable[Zone], pipette: Decimal) -> list[Zone]:
    """POI puanı #3: geçerli, kullanılabilir daha üst TF zonları (4H/D) içinde kalıyorsa."""
    zd, lo, hi = z.tf.delta, z.bottom + pipette, z.top - pipette        # contained_in(z, p): p.bottom ≤ z.bottom+pip ve p.top ≥ z.top−pip (en ucuz testler önce)
    return [p for p in parents if p.kind is z.kind and p.bottom <= lo and p.top >= hi and p.tf.delta > zd and p.valid and p.usable]


def refined_zones(poi: Zone, lower: Iterable[Zone], pipette: Decimal) -> list[Zone]:
    """D-02: 4H POI'nin içindeki geçerli rafine M15 zonları (bunlardan birine dokunulması beklenir)."""
    pd, lo, hi, kind = poi.tf.delta, poi.bottom - pipette, poi.top + pipette, poi.kind
    return [z for z in lower if z.kind is kind and z.bottom >= lo and z.top <= hi and z.tf.delta < pd and z.valid and z.usable]
