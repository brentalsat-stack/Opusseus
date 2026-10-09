"""Market structure motoru: swing (MS-R006..R009, R014) + internal (MS-R002..R005) + MarketState.

Tasarım:
  * Yalnızca KAPANMIŞ mumlarla güncellenir (`Candle.complete`).
  * Bearish mantık, bullish mantığın fiyat işareti çevrilmiş (aynalanmış) halidir: `s = +1/-1`
    yönüyle "ileri" uçlar `_hi`, "geri" uçlar `_lo` olarak okunur. Tek kod yolu → simetri garantisi.
  * Kırılım = en az 1 pipette aşım; eşitlik kırılım değildir (MS-R001).
  * Cold start (U-15) tanımsız: `start(history, seed)` ile başlangıç durumu AÇIKÇA verilir; Seed yoksa olay üretilmez.
Açık noktalar Q-S01..Q-S06 için photon/structure/README.md.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from ..data.models import Candle, Timeframe
from .models import (Diagnostic, EventType, InternalRef, Kind, MarketState, Seed, Strength, StructureEvent,
                     SwingPoint, Trend)
from .params import StructureParams

log = logging.getLogger(__name__)


@dataclass
class _Run:
    """Trend yönündeki uç (BULL: high, BEAR: low). `price` ham fiyat."""
    price: Decimal
    index: int
    confirmed: bool


class StructureEngine:
    def __init__(self, tf: Timeframe, params: StructureParams, resolver=None,
                 live_from: Optional[datetime] = None):
        """`resolver`: outside bar sırası için alt TF çözücüsü (`SubTfResolver`); yoksa OUTSIDE_BAR işaretlenir (Q-S04).
        `live_from`: bu zamandan önceki olaylar warm-up sayılır (sinyal üretmez; Q-S01)."""
        self.tf, self.p, self.resolver, self.live_from = tf, params, resolver, live_from
        self.auto = False               # otomatik warm-up (Q-S01) — cold start tanımsız, ilk BOS'a kadar UNDEFINED
        self._bh: Optional[_Run] = None  # bootstrap: en yüksek tepe
        self._bl: Optional[_Run] = None  # bootstrap: en düşük dip (ham fiyat)
        self._bh_min: Optional[Decimal] = None
        self._bl_max: Optional[Decimal] = None
        self.H: list[Decimal] = []
        self.L: list[Decimal] = []
        self.C: list[Decimal] = []
        self.T: list = []
        self.events: list[StructureEvent] = []
        self.swing_log: list[SwingPoint] = []      # oluşan strong noktalar + onaylanan swing uçları (likidite seviyeleri için)
        self.diagnostics: list[Diagnostic] = []    # Q-S03 köşe durumları (sayaç + örnek)
        # swing
        self.s = 0                      # +1 BULL, -1 BEAR, 0 tanımsız
        self.strong: Optional[tuple[Decimal, int]] = None   # (ham fiyat, indeks)
        self.run: Optional[_Run] = None
        self._min_after: Optional[Decimal] = None           # dönüştürülmüş uzayda geri çekilme dibi
        # internal
        self.e = 0
        self.iref: Optional[tuple[Decimal, int]] = None
        self.ipend: Optional[tuple[Decimal, int]] = None

    # ---- dönüştürülmüş okumalar (s>0: olduğu gibi, s<0: aynalı) ----
    def _hi(self, i: int, s: int) -> Decimal:
        return self.H[i] if s > 0 else -self.L[i]

    def _lo(self, i: int, s: int) -> Decimal:
        return self.L[i] if s > 0 else -self.H[i]

    def _cl(self, i: int, s: int) -> Decimal:
        return self.C[i] * s

    @staticmethod
    def _trend(s: int) -> Trend:
        return Trend.BULL if s > 0 else Trend.BEAR

    def _ingest(self, c: Candle) -> int:
        if not c.complete:
            raise ValueError("yapı yalnızca KAPANMIŞ mumlarla güncellenir (complete=False)")
        if c.tf is not self.tf:
            raise ValueError(f"motor TF {self.tf.value}, gelen mum {c.tf.value}")
        if self.T and c.open_time <= self.T[-1]:
            raise ValueError(f"mum sırası bozuk: {c.open_time} <= {self.T[-1]}")
        self.H.append(c.high); self.L.append(c.low); self.C.append(c.close); self.T.append(c.open_time)
        return len(self.H) - 1

    # ---- başlatma ----
    def start(self, history: list[Candle], seed: Seed) -> None:
        """Cold start yerine açık başlangıç (U-15). `history` sessizce yüklenir; seed'den sonraki
        mumlar normal kurallarla işlenir ve olay üretirse seed tutarsızdır → ValueError."""
        if self.T:
            raise RuntimeError("motor zaten başlatıldı")
        for c in history:
            self._ingest(c)
        n = len(history)
        for name, idx in (("swing_high_index", seed.swing_high_index), ("swing_low_index", seed.swing_low_index),
                          ("internal_ref_index", seed.internal_ref_index)):
            if not 0 <= idx < n:
                raise ValueError(f"seed.{name}={idx} history dışında (0..{n - 1})")
        if seed.swing_trend not in (Trend.BULL, Trend.BEAR) or seed.internal_trend not in (Trend.BULL, Trend.BEAR):
            raise ValueError("seed trendleri BULL veya BEAR olmalı")
        s = 1 if seed.swing_trend is Trend.BULL else -1
        run_idx, strong_idx = (seed.swing_high_index, seed.swing_low_index) if s > 0 else \
            (seed.swing_low_index, seed.swing_high_index)
        if run_idx <= strong_idx and s > 0 or run_idx <= strong_idx and s < 0:
            raise ValueError("seed: trend yönündeki uç, güçlü uçtan SONRA oluşmuş olmalı")
        self.s = s
        self.strong = (s * self._lo(strong_idx, s), strong_idx)
        self.run = _Run(s * self._hi(run_idx, s), run_idx, seed.swing_high_confirmed)
        self._min_after = None
        self.e = 1 if seed.internal_trend is Trend.BULL else -1
        self.iref = (self.e * self._lo(seed.internal_ref_index, self.e), seed.internal_ref_index)
        self.ipend = None
        self._log_strong(s)
        for t in range(max(run_idx, seed.internal_ref_index) + 1, n):
            ev = self._step_swing(t) + self._step_internal(t)
            if any(x.type in (EventType.BOS, EventType.CHOCH) for x in ev):
                raise ValueError(f"seed tutarsız: history[{t}] seed'den sonra {ev[0].type.value} üretiyor")

    def start_auto(self) -> None:
        """Otomatik warm-up (Q-S01): trend ilk kapanışlı swing BOS'a kadar UNDEFINED; o ana kadar olay yok."""
        if self.T:
            raise RuntimeError("motor zaten başlatıldı")
        self.auto = True

    @property
    def ready(self) -> bool:
        """Trend tanımlı VE warm-up bitti → sinyal üretilebilir."""
        return self.s != 0 and (self.live_from is None or (bool(self.T) and self.T[-1] >= self.live_from))

    # ---- ana giriş ----
    def update(self, c: Candle) -> list[StructureEvent]:
        i = self._ingest(c)
        if self.s == 0:
            ev = self._bootstrap(i) if self.auto else []   # Seed/auto yok → olay yok (U-15)
        else:
            ev = self._step_swing(i) + self._step_internal(i)
        self.events.extend(ev)
        return ev

    # ---- bootstrap: ilk BOS'a kadar (Q-S07: MS-R006/R008'in iki yönlü uygulanması) ----
    def _bootstrap(self, t: int) -> list[StructureEvent]:
        pip = self.p.pipette
        for s, run in ((1, self._bh), (-1, self._bl)):
            # onaylı swing high/low kapanışla kırıldı mı? (MS-R006) → trend belli olur, kutu kuralı (MS-R007)
            if run is not None and run.confirmed and self._cl(t, s) - s * run.price >= pip:
                k = min(range(run.index, t + 1), key=lambda j: (self._lo(j, s), j))
                self.s = s
                self.strong = (s * self._lo(k, s), k)
                self.run = _Run(s * self._hi(t, s), t, False)
                self._min_after = None
                old = self._point(Kind.HIGH if s > 0 else Kind.LOW, run.price, run.index, Strength.WEAK, True)
                self.e = s                       # iç yapı BOS yönünde başlar; referans = kırılım öncesi en yakın aday
                self.ipend = None
                self.iref = None
                for i in range(t - 1, run.index - 1, -1):
                    if self._lo(i, s) - self._lo(i + 1, s) < pip:
                        self.iref = (s * self._lo(i, s), i)
                        break
                self._log_strong(s)
                return [self._mk_event(EventType.BOS, self._trend(s), run.price, t, True, old, "BOOTSTRAP", "MS-R006/R007",
                                       level_index=run.index, origin_index=k)]
        thr = self.p.min_pullback_pips * self.p.pip_size
        for s in (1, -1):
            run = self._bh if s > 0 else self._bl
            if run is not None and run.confirmed:
                continue                          # onaylı uç sabit; wick aşımı = sweep
            hi = self._hi(t, s)
            if run is None or hi - s * run.price >= pip:
                new = _Run(s * hi, t, False)
                if s > 0:
                    self._bh, self._bh_min = new, None
                else:
                    self._bl, self._bl_max = new, None
                continue
            lo = self._lo(t, s)
            cur = self._bh_min if s > 0 else self._bl_max
            cur = lo if cur is None else min(cur, lo)
            if s > 0:
                self._bh_min = cur
            else:
                self._bl_max = cur
            pull = s * run.price - cur
            if pull >= thr if self.p.threshold_inclusive else pull > thr:
                conf = _Run(run.price, run.index, True)   # MS-R008
                if s > 0:
                    self._bh = conf
                else:
                    self._bl = conf
        return []

    # ---- swing: MS-R006, R007, R008, R009, R014 ----
    def _mk_event(self, typ, dir_, level, idx, by_close, ref=None, note="", rule="",
                  level_index=None, origin_index=None) -> StructureEvent:
        warm = self.live_from is not None and self.T[idx] < self.live_from
        return StructureEvent(self.tf, typ, dir_, level, idx, self.T[idx], by_close, ref, note, rule, warm,
                              level_index, origin_index)

    def _log_strong(self, s: int) -> None:
        sp, si = self.strong
        self.swing_log.append(self._point(Kind.LOW if s > 0 else Kind.HIGH, sp, si, Strength.STRONG, True))

    def _point(self, kind: Kind, price: Decimal, idx: int, strength: Strength, confirmed: bool) -> SwingPoint:
        return SwingPoint(self.tf, price, idx, kind, strength, confirmed)

    def _step_swing(self, t: int) -> list[StructureEvent]:
        s, pip = self.s, self.p.pipette
        sp, si = self.strong
        cl = self._cl(t, s)
        # MS-R009/R014: strong swing'in KAPANIŞLA kırılması = trend değişimi (karşı yönde BOS)
        if s * sp - cl >= pip:
            lo_i = min(range(si, t + 1), key=lambda k: (-self._hi(k, s), k))   # kutunun ters ucu, en erken
            new_strong = (s * self._hi(lo_i, s), lo_i)
            old = self._point(Kind.LOW if s > 0 else Kind.HIGH, sp, si, Strength.STRONG, True)
            self.s = -s
            self.strong = new_strong
            self.run = _Run(self.s * self._hi(t, self.s), t, False)
            self._min_after = None
            self._log_strong(self.s)
            return [self._mk_event(EventType.BOS, self._trend(self.s), sp, t, True, old, rule="MS-R009",
                                   level_index=si, origin_index=lo_i)]
        r = self.run
        # MS-R006/R007: onaylı swing high'ın üstünde KAPANIŞ → BOS; kutu kuralıyla yeni strong low
        if r.confirmed and cl - s * r.price >= pip:
            k = min(range(r.index, t + 1), key=lambda j: (self._lo(j, s), j))
            old = self._point(Kind.HIGH if s > 0 else Kind.LOW, r.price, r.index, Strength.WEAK, True)
            self.strong = (s * self._lo(k, s), k)
            self.run = _Run(s * self._hi(t, s), t, False)
            self._min_after = None
            self._log_strong(s)
            return [self._mk_event(EventType.BOS, self._trend(s), r.price, t, True, old, rule="MS-R006/R007",
                                   level_index=r.index, origin_index=k)]
        if r.confirmed:
            return []   # wick ile geçip içeride kapanış = BOS değil (MS-R006)
        # MS-R008: onaysız uç — yeni uç mu, yoksa geri çekilme mi?
        if self._hi(t, s) - s * r.price >= pip:
            self.run = _Run(s * self._hi(t, s), t, False)
            self._min_after = None
            return []
        lo = self._lo(t, s)
        self._min_after = lo if self._min_after is None else min(self._min_after, lo)
        pullback = s * r.price - self._min_after
        thr = self.p.min_pullback_pips * self.p.pip_size
        ok = pullback >= thr if self.p.threshold_inclusive else pullback > thr
        if ok and (r.index - si + 1) >= self.p.min_swing_candles:
            self.run = _Run(r.price, r.index, True)
            kind = Kind.HIGH if s > 0 else Kind.LOW
            self.swing_log.append(self._point(kind, r.price, r.index, Strength.WEAK, True))
            return [self._mk_event(EventType.SWING_CONFIRMED, self._trend(s), r.price, t, False,
                                   self._point(kind, r.price, r.index, Strength.WEAK, True), rule="MS-R008")]
        return []

    # ---- internal: MS-R002, R003, R004, R005 ----
    def _resolve_order(self, t: int) -> Optional[str]:
        """Outside bar (Q-S04): hangi seviye önce kırıldı? 'REF' | 'PEND' | None (çözülemedi)."""
        if self.resolver is None:
            return None
        ref_p, pend_p = self.iref[0], self.ipend[0]
        up, down = (pend_p, ref_p) if self.e > 0 else (ref_p, pend_p)
        first = self.resolver.first_touch(self.tf, self.T[t], up, down, self.p.pipette)
        if first is None:
            return None
        return ("PEND" if first == "UP" else "REF") if self.e > 0 else ("REF" if first == "UP" else "PEND")

    def _apply_ref_break(self, t: int, note: str) -> list[StructureEvent]:
        """MS-R005: geçerli internal low wick ile kırıldı → CHoCH; yeni referans = en yakın internal high (MS-R003 simetrik)."""
        e, pip = self.e, self.p.pipette
        ref_price, ref_idx = self.iref
        new_ref = None
        for i in range(t - 1, ref_idx - 1, -1):
            if self._hi(i + 1, e) - self._hi(i, e) < pip:        # MS-R002: i+1, i'nin high'ını kıramadı
                new_ref = (e * self._hi(i, e), i)
                break
        if new_ref is None:
            adv = "high" if e > 0 else "low"           # CHoCH öncesi iç yapının 'ileri' ucu (bullish: high, bearish: low)
            self.diagnostics.append(Diagnostic(
                "Q-S03b", t, self.T[t],
                f"CHoCH ({self.T[t]:%Y-%m-%d %H:%M}) sonrası internal referans yok: [{ref_idx}..{t - 1}] aralığında "
                f"'sonraki mumun {adv}'ı onu kıramadı' koşulunu sağlayan aday yok; kırılış mumunun {adv}'ı "
                f"({e * self._hi(t, e)}) önceki mumunkini ({e * self._hi(t - 1, e)}) aştı ve aralıkta her mum yeni {adv} yaptı"))
            log.debug("%s idx=%d Q-S03b", self.tf.value, t)
        origin = self.ipend[1] if self.ipend is not None else (new_ref[1] if new_ref is not None else t - 1)
        self.e, self.iref, self.ipend = -e, new_ref, None
        return [self._mk_event(EventType.CHOCH, self._trend(self.e), ref_price, t, False, None, note, "MS-R005",
                               level_index=ref_idx, origin_index=origin)]

    def _apply_pend_break(self, t: int) -> list[StructureEvent]:
        """MS-R003: internal high wick ile kırıldı → yeni internal low = kırılımdan önceki EN YAKIN aday low."""
        e, pip = self.e, self.p.pipette
        pend_idx = self.ipend[1]
        found = None
        for i in range(t - 1, pend_idx - 1, -1):
            if self._lo(i, e) - self._lo(i + 1, e) < pip:        # i+1, i'nin low'unu kıramadı
                found = (e * self._lo(i, e), i)
                break
        self.ipend = None
        if found is None:
            back = "low" if e > 0 else "high"          # pullback ucu (bullish: low, bearish: high)
            self.diagnostics.append(Diagnostic(
                "Q-S03a", t, self.T[t],
                f"internal {'high' if e > 0 else 'low'} ({self.T[t]:%Y-%m-%d %H:%M}) kırıldı ama [{pend_idx}..{t - 1}] içinde "
                f"aday internal {back} yok: pullback boyunca her mum yeni {back} yapmış ve kırılış mumunun {back}'ı "
                f"({e * self._lo(t, e)}) önceki mumunkini ({e * self._lo(t - 1, e)}) geçti → referans DEĞİŞMEDİ"))
            log.debug("%s idx=%d Q-S03a", self.tf.value, t)
            return []
        self.iref = found
        return [self._mk_event(EventType.INTERNAL_REF, self._trend(e), found[0], t, False, None, rule="MS-R003")]

    def _step_internal(self, t: int) -> list[StructureEvent]:
        e, pip = self.e, self.p.pipette
        hi, lo = self._hi(t, e), self._lo(t, e)
        broke_ref = self.iref is not None and e * self.iref[0] - lo >= pip
        broke_pend = self.ipend is not None and hi - e * self.ipend[0] >= pip
        if broke_ref and broke_pend:
            # Q-S04: mum içi sıra alt TF verisiyle çözülür; çözülemezse varsayım YOK → OUTSIDE_BAR (sinyal yok, durum değişmez)
            order = self._resolve_order(t)
            if order is None:
                return [self._mk_event(EventType.OUTSIDE_BAR, Trend.UNDEFINED, self.iref[0], t, False,
                                       None, "UNRESOLVED", "MS-R005")]
            if order == "REF":
                return self._apply_ref_break(t, "OUTSIDE_BAR_RESOLVED")
            evs = self._apply_pend_break(t)       # önce high kırıldı → yeni referans; sonra low da yeni referansı kırdıysa CHoCH
            if self.iref is not None and e * self.iref[0] - lo >= pip:
                evs += self._apply_ref_break(t, "OUTSIDE_BAR_RESOLVED")
            return evs
        if broke_ref:
            return self._apply_ref_break(t, "")
        if broke_pend:
            return self._apply_pend_break(t)
        # MS-R002: yeni mum önceki mumun high'ını kıramadıysa önceki mumun high'ı aday internal high
        if self.ipend is None and t >= 1 and (self.iref is None or t - 1 > self.iref[1]):
            if hi - self._hi(t - 1, e) < pip:
                self.ipend = (e * self._hi(t - 1, e), t - 1)
        return []

    # ---- durum ----
    def state(self) -> MarketState:
        sh = sl = None
        eq = None
        if self.s != 0:
            r, (sp, si) = self.run, self.strong
            if self.s > 0:
                sh = self._point(Kind.HIGH, r.price, r.index, Strength.WEAK, r.confirmed)
                sl = self._point(Kind.LOW, sp, si, Strength.STRONG, True)
            else:
                sl = self._point(Kind.LOW, r.price, r.index, Strength.WEAK, r.confirmed)
                sh = self._point(Kind.HIGH, sp, si, Strength.STRONG, True)
            if r.confirmed:   # Q-S06: P/D aralığı AMBIGUOUS; yalnız onaylı swing aralığında EQ verilir
                eq = sl.price + (sh.price - sl.price) / 2
        ih = il = None
        if self.iref is not None:
            ref = InternalRef(self.iref[0], self.iref[1])
            ih, il = (None, ref) if self.e > 0 else (ref, None)
        return MarketState(self.tf, self._trend(self.s) if self.s else Trend.UNDEFINED, sh, sl,
                           self._trend(self.e) if self.e else Trend.UNDEFINED, ih, il, eq)
