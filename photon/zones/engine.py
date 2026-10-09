"""Zon yaşam döngüsü: oluşturma (SD-R001/R002), tür (SD-R003), yapıya bağlama (SD-R005), mitigation, invalidation,
flip / failed reaction (SD-R006). Yalnızca kapanmış mumlarla; her TF için bir motor, aynı TF'nin StructureEngine'i ile
birlikte çalışır (önce yapı motoru `update`, sonra `ZoneEngine.update(candle, events)`).

Bearish (supply) mantığı bullish (demand) mantığının aynalanmış halidir (s = +1/−1)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from ..data.models import Candle, Timeframe
from ..structure.engine import StructureEngine
from ..structure.models import EventType, StructureEvent, Trend
from .detect import pivot_zone, range_zone
from .models import Context, Origin, Zone, ZoneKind

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ZoneParams:
    pip_size: Decimal
    draw_mode: str               # config zone_draw_mode.<TF>
    min_chain: int               # range_detection.min_candles
    reaction_min_pips: Decimal   # reaction_min.pips (SD-R006)
    eqh_tol_pips: Decimal        # eqh_tolerance.pips (LQ-R001/R002)

    @property
    def pipette(self) -> Decimal:
        return self.pip_size / 10

    @classmethod
    def from_config(cls, cfg, pair: str, tf: Timeframe) -> "ZoneParams":
        cfg.require("zones", "liquidity")
        mode = cfg.get(f"zone_draw_mode.{tf.value}")
        if mode is None:
            # D1 için çizim modu kararı yok (Q-Z3); varsayılan atanmaz
            raise ValueError(f"zone_draw_mode.{tf.value} tanımsız (Q-Z3)")
        return cls(cfg.pip_size(pair), mode, cfg.get("range_detection.min_candles"),
                   Decimal(str(cfg.get("reaction_min.pips"))), Decimal(str(cfg.get("eqh_tolerance.pips"))))


@dataclass
class _Track:
    """Bir zon için flip izleme durumu (dönüştürülmüş uzay: talepte fiyat aşağı = derinleşme)."""
    target: Decimal                    # tepki hedefi: zon yaratıldığından dokunuşa kadarki en yüksek uç
    rs: Decimal                        # tepki başlangıcı (en derin uç)
    rs_idx: int
    rt: Optional[Decimal] = None       # tepki ucu (rs'den sonraki en yüksek uç)


class ZoneEngine:
    def __init__(self, tf: Timeframe, params: ZoneParams, structure: StructureEngine):
        self.tf, self.p, self.structure = tf, params, structure
        self.candles: list[Candle] = []
        self.zones: list[Zone] = []
        self._tracks: dict[str, _Track] = {}
        self._prev_trend: Trend = Trend.UNDEFINED
        self._seq = 0

    # ---- yardımcılar (s>0: talep, aynasız) ----
    @staticmethod
    def _s(z: Zone) -> int:
        return 1 if z.kind is ZoneKind.DEMAND else -1

    @staticmethod
    def _hi(c: Candle, s: int) -> Decimal:
        return c.high if s > 0 else -c.low

    @staticmethod
    def _lo(c: Candle, s: int) -> Decimal:
        return c.low if s > 0 else -c.high

    def touches(self, z: Zone, c: Candle) -> bool:
        """Mitigation (DERIVED, Q-Z4): mum zonla kesişir (talepte low ≤ top, arzda high ≥ bottom)."""
        return c.low <= z.top and c.high >= z.bottom

    def sweep_flag(self, z: Zone) -> bool:
        """LQ-R002 (tembel + önbellekli): zon oluşurken likidite süpürüldü mü. Yalnızca POI adayları için hesaplanır."""
        if z.is_sweep is None:
            from ..liquidity.sweeps import is_sweep_zone
            z.is_sweep = is_sweep_zone(z, self.candles, self.structure.swing_log,
                                       self.p.eqh_tol_pips * self.p.pip_size, self.p.pipette)
        return z.is_sweep

    def active(self) -> list[Zone]:
        return [z for z in self.zones if z.usable]

    # ---- ana giriş ----
    def update(self, c: Candle, events: list[StructureEvent]) -> list[Zone]:
        """Yapı motoru bu mumu işledikten SONRA çağrılır. Bu mumda doğan zonları döner."""
        if c.tf is not self.tf:
            raise ValueError(f"motor TF {self.tf.value}, gelen {c.tf.value}")
        if not c.complete:
            raise ValueError("zonlar yalnızca KAPANMIŞ mumlarla güncellenir")
        self.candles.append(c)
        t = len(self.candles) - 1
        new: list[Zone] = []
        for z in self.active():
            if z.created_index < t:
                f = self._advance(z, t)
                if f is not None:
                    new.append(f)
        new += self._detect(t)
        self._link(events, t)
        self._prev_trend = self.structure.state().swing_trend
        return new

    # ---- oluşturma ----
    def _mk(self, kind, origin, draw, top, bottom, first, t, ctx=None, flip_from=None) -> Zone:
        self._seq += 1
        c = self.candles[t]
        z = Zone(f"{self.tf.value}-{t}-{origin.value[0]}{self._seq}", self.tf, kind, origin, draw, top, bottom,
                 first, t, c.open_time, ctx, is_flip=flip_from is not None, flipped_from=flip_from,
                 warmup=self.structure.live_from is not None and c.open_time < self.structure.live_from)
        self.zones.append(z)
        return z

    def _context(self, kind: ZoneKind) -> Optional[Context]:
        """SD-R003: zondan önceki yön (TF swing trendi) zonla aynıysa continuation."""
        if self._prev_trend is Trend.UNDEFINED:
            return None
        return Context.CONTINUATION if self._prev_trend is kind.direction else Context.REVERSAL

    def _detect(self, t: int) -> list[Zone]:
        out = []
        pip = self.p.pipette
        mode = "CANDLE" if self.p.draw_mode == "CANDLE" else "RANGE"
        for g in (pivot_zone(self.candles, t, pip, mode),
                  range_zone(self.candles, t, pip, self.p.min_chain)):
            if g is not None:
                out.append(self._mk(g.kind, g.origin, g.draw, g.top, g.bottom, g.first_index, t, self._context(g.kind)))
        return out

    # ---- yapıya bağlama: SD-R005 ("zon X yapı kırılımına neden oldu") ----
    def _link(self, events: list[StructureEvent], t: int) -> None:
        """Olay E (BOS/CHoCH, yön d): kırılımı yapan hareketin başladığı uçtan (E.origin_index) kırılım mumuna kadar
        doğan, aynı yönlü (BULL→talep, BEAR→arz) zonlardan EN ERKEN doğan neden olur; ayrıca aynı pencerede doğan
        flip zonları da (SD-R007: flip + CHoCH/BOS) bağlanır. Onaylı algoritma: Q-Z5."""
        for ev in events:
            if ev.type not in (EventType.BOS, EventType.CHOCH) or ev.origin_index is None:
                continue
            kind = ZoneKind.DEMAND if ev.dir is Trend.BULL else ZoneKind.SUPPLY
            cands = [z for z in self.zones if z.kind is kind and ev.origin_index <= z.created_index <= ev.break_index]
            plain = [z for z in cands if not z.is_flip]
            if plain:
                first = min(plain, key=lambda z: (z.created_index, 0 if z.origin is Origin.PIVOT else 1))
                first.caused_events.append(ev)
            for z in cands:
                if z.is_flip:
                    z.caused_events.append(ev)

    # ---- mitigation / flip / invalidation ----
    def _advance(self, z: Zone, t: int) -> Optional[Zone]:
        c = self.candles[t]
        s, pip = self._s(z), self.p.pipette
        flip: Optional[Zone] = None
        if z.fulfilled_index is None:
            tr = self._tracks.get(z.id)
            if tr is None:
                if self.touches(z, c):
                    if z.mitigated_index is None:
                        z.mitigated_index = t
                    target = max(self._hi(self.candles[k], s) for k in range(z.created_index, t))
                    self._tracks[z.id] = _Track(target, self._lo(c, s), t)   # dokunuş mumunun kendi tepkisi sayılmaz (sıra bilinmiyor)
            else:
                lo, hi = self._lo(c, s), self._hi(c, s)
                if tr.rs - lo >= pip:                          # tepki başlangıcı ≥1 pipette aşıldı
                    if z.valid and tr.rt is not None and tr.rt - tr.rs >= self.p.reaction_min_pips * self.p.pip_size:
                        flip = self._make_flip(z, tr, t)       # SD-R006: failed reaction (ön koşul: geçerli zon)
                    else:                                       # tepkisiz düz geçiş → flip değil; başlangıç derinleşir
                        tr.rs, tr.rs_idx, tr.rt = lo, t, None
                else:
                    tr.rt = hi if tr.rt is None else max(tr.rt, hi)
                    if hi - tr.target >= pip:                   # hedef kırıldı → zon görevini yaptı
                        z.fulfilled_index = t
                        self._tracks.pop(z.id, None)
        # invalidation: karşı uçtan KAPANIŞLA geçildi
        beyond = z.bottom - c.close if s > 0 else c.close - z.top
        if z.usable and beyond >= pip:
            z.invalidated_index = t
            self._tracks.pop(z.id, None)
        return flip

    def _make_flip(self, z: Zone, tr: _Track, t: int) -> Zone:
        s = self._s(z)
        a, b = s * tr.rs, s * tr.rt
        z.flipped_index = t
        self._tracks.pop(z.id, None)
        f = self._mk(z.kind.opposite, Origin.FLIP, "REACTION", max(a, b), min(a, b), tr.rs_idx, t,
                     Context.REVERSAL, flip_from=z.id)
        log.debug("flip %s -> %s @%d", z.id, f.id, t)
        return f
