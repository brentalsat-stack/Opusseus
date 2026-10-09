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
    return [p for p in parents if p.tf.delta > z.tf.delta and p.valid and p.usable and contained_in(z, p, pipette)]


def refined_zones(poi: Zone, lower: Iterable[Zone], pipette: Decimal) -> list[Zone]:
    """D-02: 4H POI'nin içindeki geçerli rafine M15 zonları (bunlardan birine dokunulması beklenir)."""
    return [z for z in lower if z.tf.delta < poi.tf.delta and z.valid and z.usable and contained_in(z, poi, pipette)]
