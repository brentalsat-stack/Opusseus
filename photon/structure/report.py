"""Doğrulama çıktıları: olay CSV'si ve işaretli grafik (Aşama 2 'ek çıktı'). Kural mantığı içermez."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import yaml

from ..data.models import Candle, Timeframe
from .engine import StructureEngine
from .models import EventType, Seed, StructureEvent, Trend
from .params import StructureParams

_COLS = ["time_utc", "tf", "type", "dir", "level", "break_index", "by_close", "rule", "note", "warmup",
         "ref_index", "ref_price", "ref_confirmed"]


def load_seed_yaml(path: str | Path, candles: Sequence[Candle]) -> tuple[Seed, int]:
    """Zaman damgalı seed dosyasını (Q-S01) indeksli Seed'e çevirir. Döner: (seed, history uzunluğu)."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    pos = {c.open_time: i for i, c in enumerate(candles)}

    def idx(key: str) -> int:
        t = raw[key]
        t = t if isinstance(t, datetime) else datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        t = t.replace(tzinfo=t.tzinfo or __import__("datetime").timezone.utc)
        if t not in pos:
            raise ValueError(f"seed.{key}={t.isoformat()} mum serisinde yok")
        return pos[t]

    seed = Seed(Trend(raw["swing_trend"]), idx("swing_high_time"), idx("swing_low_time"),
                bool(raw["swing_high_confirmed"]), Trend(raw["internal_trend"]), idx("internal_ref_time"))
    return seed, max(seed.swing_high_index, seed.swing_low_index, seed.internal_ref_index) + 1


def run_structure(candles: Sequence[Candle], params: StructureParams, seed: Seed,
                  history_len: int, resolver=None, live_from: datetime | None = None) -> StructureEngine:
    """Elle seed seçeneği (Q-S01)."""
    eng = StructureEngine(candles[0].tf, params, resolver, live_from)
    eng.start(list(candles[:history_len]), seed)
    for c in candles[history_len:]:
        eng.update(c)
    return eng


def run_structure_auto(candles: Sequence[Candle], params: StructureParams, live_from: datetime,
                       resolver=None) -> StructureEngine:
    """Otomatik warm-up (Q-S01): `candles` warm-up başlangıcından itibaren; `live_from` öncesi olaylar warmup=True."""
    eng = StructureEngine(candles[0].tf, params, resolver, live_from)
    eng.start_auto()
    for c in candles:
        eng.update(c)
    return eng


def write_events_csv(events: Iterable[StructureEvent], path: str | Path) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_COLS)
        for e in events:
            r = e.ref
            w.writerow([e.time.strftime("%Y-%m-%dT%H:%M:%SZ"), e.tf.value, e.type.value, e.dir.value,
                        e.level, e.break_index, e.by_close, e.rule, e.note, e.warmup,
                        r.index if r else "", r.price if r else "", r.confirmed if r else ""])
            n += 1
    return n


_STYLE = {  # (renk, işaret, etiket)
    (EventType.BOS, Trend.BULL): ("#1b7f3b", "^", "BOS↑"), (EventType.BOS, Trend.BEAR): ("#b3261e", "v", "BOS↓"),
    (EventType.CHOCH, Trend.BULL): ("#0b63c4", "^", "CHoCH↑"), (EventType.CHOCH, Trend.BEAR): ("#c46a0b", "v", "CHoCH↓"),
    (EventType.SWING_CONFIRMED, Trend.BULL): ("#555555", "o", "swing ✓"), (EventType.SWING_CONFIRMED, Trend.BEAR): ("#555555", "o", "swing ✓"),
    (EventType.OUTSIDE_BAR, Trend.UNDEFINED): ("#999999", "x", "OUTSIDE_BAR (sinyal yok)"),
}


def plot_events(candles: Sequence[Candle], events: Sequence[StructureEvent], path: str | Path,
                title: str = "", first_index: int = 0) -> None:
    """`first_index`'ten itibaren çizer (warm-up bölümünü atlamak için); olay indeksleri mutlak kalır."""
    events = [e for e in events if e.break_index >= first_index]
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(max(10, (len(candles) - first_index) * 0.12), 6))
    for i, c in enumerate(candles):
        if i < first_index:
            continue
        up = c.close >= c.open
        col = "#2e7d32" if up else "#c62828"
        ax.plot([i, i], [float(c.low), float(c.high)], color=col, lw=0.8)
        ax.plot([i, i], [float(c.open), float(c.close)], color=col, lw=3)
    seen = set()
    for e in events:
        st = _STYLE.get((e.type, e.dir))
        if st is None:
            continue
        color, marker, label = st
        y = float(candles[e.break_index].high if e.dir is Trend.BULL else candles[e.break_index].low)  # UNDEFINED → low
        ax.scatter([e.break_index], [y], c=color, marker=marker, s=60, zorder=5,
                   label=None if label in seen else label)
        seen.add(label)
        if e.type in (EventType.BOS, EventType.CHOCH):
            start = e.ref.index if e.ref else max(0, e.break_index - 20)
            ax.hlines(float(e.level), start, e.break_index, colors=color, linestyles="--", lw=0.9)
    ax.set_title(title or f"{candles[0].pair} {candles[0].tf.value}")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_xlabel("mum indeksi")
    fig.tight_layout()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=110)
    plt.close(fig)
