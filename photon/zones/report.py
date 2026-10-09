"""Zon doğrulama çıktıları: CSV ve grafik (Aşama 4 'ek çıktı'). Kural mantığı içermez."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ..data.models import Candle
from ..structure.engine import StructureEngine
from ..structure.models import EventType
from ..structure.params import StructureParams
from .engine import ZoneEngine, ZoneParams
from .models import Origin, Zone, ZoneKind

_COLS = ["id", "tf", "kind", "origin", "draw", "top", "bottom", "created_time", "first_index", "created_index",
         "context", "valid", "caused_by", "is_flip", "flipped_from", "mitigated_time", "invalidated_time",
         "flipped_time", "fulfilled_time", "warmup", "sweep_zone"]


def run_zones(candles: Sequence[Candle], sparams: StructureParams, zparams: ZoneParams, live_from: datetime,
              resolver=None) -> tuple[StructureEngine, ZoneEngine]:
    """Otomatik warm-up'lı yapı motoru ile zon motorunu aynı mum akışında sürer."""
    st = StructureEngine(candles[0].tf, sparams, resolver, live_from)
    st.start_auto()
    ze = ZoneEngine(candles[0].tf, zparams, st)
    for c in candles:
        ev = st.update(c)
        ze.update(c, ev)
    return st, ze


def _t(candles: Sequence[Candle], i: Optional[int]) -> str:
    return "" if i is None else candles[i].open_time.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_zones_csv(zones: Iterable[Zone], candles: Sequence[Candle], path: str | Path,
                    ze: Optional[ZoneEngine] = None) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_COLS)
        for z in zones:
            caused = "|".join(f"{e.type.value}{e.dir.value[0]}@{e.time:%Y-%m-%dT%H:%M}" for e in z.caused_events)
            sweep = ze.sweep_flag(z) if (ze is not None and z.valid) else ""
            w.writerow([z.id, z.tf.value, z.kind.value, z.origin.value, z.draw, z.top, z.bottom,
                        z.created_time.strftime("%Y-%m-%dT%H:%M:%SZ"), z.first_index, z.created_index,
                        z.context.value if z.context else "", z.valid, caused, z.is_flip, z.flipped_from or "",
                        _t(candles, z.mitigated_index), _t(candles, z.invalidated_index), _t(candles, z.flipped_index),
                        _t(candles, z.fulfilled_index), z.warmup, sweep])
            n += 1
    return n


def summarize(zones: Sequence[Zone]) -> str:
    c = Counter((z.origin.value, z.kind.value) for z in zones)
    valid = [z for z in zones if z.valid]
    flips = [z for z in zones if z.is_flip]
    both = [z for z in zones if z.is_flip and z.caused_events]
    swing = [z for z in zones if z.caused_swing_bos]
    lines = [f"Zon özeti: toplam {len(zones)}, geçerli (SD-R005) {len(valid)}, flip {len(flips)}, flip+yapı kırılımı {len(both)}, "
             f"swing BOS'a neden olan {len(swing)}"]
    lines.append("  " + ", ".join(f"{o}/{k}={n}" for (o, k), n in sorted(c.items())))
    return "\n".join(lines)


def plot_zones(candles: Sequence[Candle], zones: Sequence[Zone], path: str | Path, first_index: int = 0,
               only_valid: bool = True, title: str = "") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    n = len(candles)
    fig, ax = plt.subplots(figsize=(max(10, (n - first_index) * 0.12), 6))
    for i in range(first_index, n):
        c = candles[i]
        col = "#2e7d32" if c.close >= c.open else "#c62828"
        ax.plot([i, i], [float(c.low), float(c.high)], color=col, lw=0.8)
        ax.plot([i, i], [float(c.open), float(c.close)], color=col, lw=3)
    shown = 0
    for z in zones:
        if only_valid and not z.valid:
            continue
        end = next((x for x in (z.invalidated_index, z.flipped_index) if x is not None), n - 1)
        if end < first_index:
            continue
        x0 = max(z.created_index, first_index)
        color = "#1b7f3b" if z.kind is ZoneKind.DEMAND else "#b3261e"
        ax.add_patch(Rectangle((x0, float(z.bottom)), end - x0 + 1, float(z.top - z.bottom), facecolor=color,
                               alpha=0.28 if not z.is_flip else 0.45, edgecolor=color, lw=0.6,
                               hatch="//" if z.is_flip else None))
        shown += 1
    lo = min(float(c.low) for c in candles[first_index:])
    hi = max(float(c.high) for c in candles[first_index:])
    ax.set_ylim(lo, hi)
    ax.set_title(title or f"{candles[0].pair} {candles[0].tf.value} zonlar ({shown} geçerli, flip=taralı)")
    ax.set_xlabel("mum indeksi")
    fig.tight_layout()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=110)
    plt.close(fig)
