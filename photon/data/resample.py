"""Resampler: tick → M1 → M15 → H4 → D1 (FINAL_SPEC §22, §23).

H4/D1 sınırları kaynakta tanımsızdır → IMPLEMENTATION DECISION REQUIRED (Q-D01):
`candle_boundaries.{tz,d1_open,h4_anchor}` config'den gelir, varsayılan yoktur.

Sınır kuralı (config değerleriyle):
  * D1 mumu: saat dilimi `tz`'de duvar saati `d1_open` olan andan bir sonraki `d1_open`'a kadar
    (DST günleri 23/25 saat sürer).
  * H4 mumu: en son `h4_anchor` anından başlayıp 4 saatlik adımlarla; bir sonraki `h4_anchor`'da
    sıfırlanır (son H4 mumu gerekirse kısa kalır).
  * M1/M5/M15: UTC epoch'a hizalı.
Eksik girdi sessizce doldurulmaz; sıralama bozuksa hata verilir.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Iterator
from zoneinfo import ZoneInfo

from .models import OHLC, QuoteCandle, Tick, Timeframe
from .tz import UTC, ensure_utc, local_to_utc

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_FIXED = {Timeframe.M1, Timeframe.M5, Timeframe.M15}


@dataclass(frozen=True)
class BoundarySpec:
    tz: ZoneInfo
    d1_open: time
    h4_anchor: time

    @classmethod
    def from_config(cls, cfg) -> "BoundarySpec":
        cfg.require("data_boundaries")
        return cls(ZoneInfo(cfg.get("candle_boundaries.tz")),
                   time.fromisoformat(cfg.get("candle_boundaries.d1_open")),
                   time.fromisoformat(cfg.get("candle_boundaries.h4_anchor")))


def _anchor_start(ts: datetime, tz: ZoneInfo, t: time) -> datetime:
    """`ts`'den önceki (veya eşit) en son yerel `t` anı, UTC."""
    local = ts.astimezone(tz)
    day = local.date() if local.time() >= t else local.date() - timedelta(days=1)
    start = local_to_utc(datetime.combine(day, t), tz)
    if start > ts:  # belirsiz (çift) saat kenarı; sessiz düzeltme yok
        raise ValueError(f"{ts}: {tz.key} {t} sınırı belirsiz (DST); config'i gözden geçirin")
    return start


def bin_bounds(ts: datetime, tf: Timeframe, spec: BoundarySpec | None) -> tuple[datetime, datetime]:
    ts = ensure_utc(ts)
    if tf in _FIXED:
        step = int(tf.delta.total_seconds())
        start = _EPOCH + timedelta(seconds=((ts - _EPOCH).total_seconds() // step) * step)
        return start, start + tf.delta
    if spec is None:
        raise ValueError(f"{tf.value} için BoundarySpec gerekli (candle_boundaries config'i)")
    if tf is Timeframe.D1:
        s = _anchor_start(ts, spec.tz, spec.d1_open)
        return s, _anchor_start(s + timedelta(hours=30), spec.tz, spec.d1_open)
    if tf is Timeframe.H4:
        ref = _anchor_start(ts, spec.tz, spec.h4_anchor)
        nxt = _anchor_start(ref + timedelta(hours=30), spec.tz, spec.h4_anchor)
        k = (ts - ref) // tf.delta
        s = ref + k * tf.delta
        return s, min(s + tf.delta, nxt)
    raise ValueError(f"desteklenmeyen TF: {tf}")


def ticks_to_m1(ticks: Iterable[Tick]) -> Iterator[QuoteCandle]:
    """Tick → M1 (bid ve ask ayrı OHLC). Boş dakikalar için mum üretilmez. Tick sırası bozuksa hata."""
    cur_start = None
    prev = None
    acc: dict | None = None
    for t in ticks:
        if prev is not None and t.time < prev:
            raise ValueError(f"sırasız tick: {t.time} < {prev}")
        prev = t.time
        start, _ = bin_bounds(t.time, Timeframe.M1, None)
        if start != cur_start:
            if acc:
                yield _finish(acc)
            cur_start = start
            acc = {"pair": t.pair, "start": start, "b": [t.bid] * 4, "a": [t.ask] * 4, "n": 0}
        for k, p in (("b", t.bid), ("a", t.ask)):
            o = acc[k]
            o[1] = max(o[1], p)
            o[2] = min(o[2], p)
            o[3] = p
        acc["n"] += 1
    if acc:
        yield _finish(acc)


def _finish(a: dict) -> QuoteCandle:
    return QuoteCandle(a["pair"], Timeframe.M1, a["start"], OHLC(*a["b"]), OHLC(*a["a"]), True, a["n"])


class MinuteAggregator:
    """Canlı akış için: tick besle, dakika kapanınca kapanmış M1 mumu(ları) döner."""

    def __init__(self) -> None:
        self._ticks: list[Tick] = []

    def feed(self, tick: Tick) -> list[QuoteCandle]:
        out: list[QuoteCandle] = []
        if self._ticks:
            if tick.time < self._ticks[-1].time:
                raise ValueError(f"sırasız tick: {tick.time} < {self._ticks[-1].time}")
            if bin_bounds(tick.time, Timeframe.M1, None)[0] != bin_bounds(self._ticks[0].time, Timeframe.M1, None)[0]:
                out = list(ticks_to_m1(self._ticks))
                self._ticks = []
        self._ticks.append(tick)
        return out


def resample(candles: Iterable[QuoteCandle], tf: Timeframe, spec: BoundarySpec | None = None) -> list[QuoteCandle]:
    """Daha ince TF mumlarını `tf`'ye toplar. Girdi tek TF, zaman sıralı ve tekrarsız olmalı.
    Son kutu, girdi verisi kutunun sonuna ulaşmadıysa `complete=False` olur."""
    out: list[QuoteCandle] = []
    group: list[QuoteCandle] = []
    group_bounds: tuple[datetime, datetime] | None = None
    src_tf = None
    last_end = None

    def flush(final: bool) -> None:
        if not group:
            return
        s, e = group_bounds
        done = all(c.complete for c in group) and (not final or last_end >= e)
        out.append(QuoteCandle(
            group[0].pair, tf, s,
            OHLC(group[0].bid.open, max(c.bid.high for c in group), min(c.bid.low for c in group), group[-1].bid.close),
            OHLC(group[0].ask.open, max(c.ask.high for c in group), min(c.ask.low for c in group), group[-1].ask.close),
            done, sum(c.n_ticks for c in group) if all(c.n_ticks is not None for c in group) else None))

    prev = None
    for c in candles:
        if src_tf is None:
            src_tf = c.tf
            if tf.delta <= src_tf.delta:
                raise ValueError(f"{tf.value}, {src_tf.value}'den kaba olmalı")
        elif c.tf is not src_tf:
            raise ValueError("karışık TF girdisi")
        if prev is not None and c.open_time <= prev:
            raise ValueError(f"girdi sıralı/tekrarsız değil: {c.open_time} <= {prev}")
        prev = c.open_time
        b = bin_bounds(c.open_time, tf, spec)
        if c.open_time + src_tf.delta > b[1]:
            raise ValueError(f"{src_tf.value} mumu {c.open_time}, {tf.value} sınırını aşıyor; boundaries kaynak ızgarasına hizalı olmalı")
        if b != group_bounds:
            flush(False)
            group, group_bounds = [], b
        group.append(c)
        last_end = c.open_time + src_tf.delta
    flush(True)
    return out
