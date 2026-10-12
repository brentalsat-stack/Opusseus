"""Zon→olay bağlaması teşhisi (SD-R005, Q-Z5): bir BOS/CHoCH için pencere mumları, her mumda pivot/range algılama sonucu ve NEDENİ,
penceredeki tüm zonlar ve aday elemesi. Yalnızca raporlar; algılamayı değiştirmez (explain_* fonksiyonları detect.py mantığının anlatımlı kopyasıdır)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence

from ..data.models import Candle
from ..structure.engine import StructureEngine
from ..structure.models import EventType, StructureEvent, Trend
from .detect import MAX_CHAIN_LOOKBACK, pivot_zone, range_zone
from .engine import ZoneEngine
from .models import Zone, ZoneKind


def explain_pivot(candles: Sequence[Candle], t: int, pipette: Decimal) -> str:
    """SD-R002 anlatımı: kopuş mumu t için neden zon çıktı / çıkmadı."""
    b = candles[t]
    if b.close == b.open:
        return "doji: yön yok"
    s = 1 if b.close > b.open else -1
    kind = "talep(STB)" if s > 0 else "arz(BTS)"
    ext, n = None, 0
    for j in range(t - 1, max(-1, t - 25), -1):
        c = candles[j]
        if s * (c.close - c.open) >= 0:
            why = f"j={j} karşı yönlü DEĞİL ({'bullish' if c.close > c.open else 'bearish' if c.close < c.open else 'doji'})"
            return (f"{kind}: koşu {n} mum — {why}" if n else f"{kind}: koşu YOK — hemen önceki mum {why}") + \
                (f"; koşu ucu {ext}" if ext is not None else "")
        e = c.high if s > 0 else -c.low
        cand = e if ext is None else max(ext, e)
        if s * b.close - cand < pipette:
            need = (cand if s > 0 else -cand)
            return (f"{kind}: j={j} yutulmuyor — kopuş kapanışı {b.close}, gereken {'>' if s > 0 else '<'} {need} ±1 pipette "
                    f"(koşu {n} mum{'; ZON YOK' if n == 0 else ''})")
        ext = cand
        n += 1
    return f"{kind}: koşu ≥ {n} mum"


def explain_range(candles: Sequence[Candle], t: int, pipette: Decimal, min_chain: int) -> str:
    """SD-R001 anlatımı: t kopuş mumu için son birkaç mother adayı neden elendi."""
    c = candles[t]
    rows = []
    mx = mn = None
    stop = max(-1, t - 1 - MAX_CHAIN_LOOKBACK)
    for m in range(t - 1, stop, -1):
        if t - 1 - m >= min_chain - 1:
            hm, lm = candles[m].high, candles[m].low
            inside = mx - hm < pipette and lm - mn < pipette
            brk = (c.close - hm >= pipette) or (lm - c.close >= pipette)
            rows.append(f"m={m}: zincir {t - m} mum, inside={'E' if inside else 'H'}, kapanışla çıkış={'E' if brk else 'H'}")
            if len(rows) >= 4:
                break
        h, l = candles[m].high, candles[m].low
        mx = h if mx is None else max(mx, h)
        mn = l if mn is None else min(mn, l)
    return "; ".join(rows) if rows else f"zincir için yeterli geçmiş mum yok (min_chain={min_chain})"


def _tstr(candles: Sequence[Candle], i: Optional[int]) -> str:
    return "-" if i is None or i >= len(candles) else candles[i].open_time.strftime("%m-%d %H:%M")


def zone_line(z: Zone, candles: Sequence[Candle]) -> str:
    ev = ",".join(f"{e.type.value}/{e.dir.value}@{_tstr(candles, e.break_index)}" for e in z.caused_events) or "-"
    st = []
    if z.mitigated_index is not None:
        st.append(f"mitigasyon {_tstr(candles, z.mitigated_index)}")
    if z.invalidated_index is not None:
        st.append(f"GEÇERSİZ {_tstr(candles, z.invalidated_index)}")
    if z.flipped_index is not None:
        st.append(f"flip {_tstr(candles, z.flipped_index)}")
    if z.fulfilled_index is not None:
        st.append(f"görevini yaptı {_tstr(candles, z.fulfilled_index)}")
    return (f"{z.id:<20}{z.kind.value:<7}{z.origin.value:<7}{z.draw:<7}[{z.bottom}–{z.top}] ilk={_tstr(candles, z.first_index)} "
            f"doğdu={_tstr(candles, z.created_index)} valid={z.valid} usable={z.usable} neden={ev} {' '.join(st)}")


def trace_events(st: StructureEngine, ze: ZoneEngine, candles: Sequence[Candle], start: datetime, end: datetime,
                 types: Sequence[EventType] = (EventType.BOS,), direction: Optional[Trend] = None, max_events: int = 12,
                 before: int = 3, after: int = 1) -> str:
    pip = ze.p.pipette
    evs = [e for e in st.events if e.type in types and (direction is None or e.dir is direction) and start <= e.time < end and e.origin_index is not None]
    L = [f"{len(evs)} olay ({', '.join(t.value for t in types)}{' ' + direction.value if direction else ''}) {start:%Y-%m-%d} → {end:%Y-%m-%d} "
         f"[{ze.tf.value}; pipette {pip}; min_chain {ze.p.min_chain}; çizim modu {ze.p.draw_mode}]"]
    for e in evs[:max_events]:
        o, b = e.origin_index, e.break_index
        kind = ZoneKind.DEMAND if e.dir is Trend.BULL else ZoneKind.SUPPLY
        L += ["", "═" * 110,
              f"{e.type.value} {e.dir.value} kırılış mumu {_tstr(candles, b)}Z (idx {b}) seviye {e.level} (seviye mumu {_tstr(candles, e.level_index)}) "
              f"origin(kutu/pullback ucu) {_tstr(candles, o)}Z (idx {o}) kural={e.rule} kapanışla={e.by_close} warmup={e.warmup} {e.note}",
              f"Q-Z5 penceresi: [{_tstr(candles, o)} … {_tstr(candles, b)}] içinde doğan {kind.value} zonlar bağlanır; en erken doğan 'neden' olur.",
              "-- mumlar --"]
        for i in range(max(0, o - before), min(len(candles), b + after + 1)):
            c = candles[i]
            col = "bullish" if c.close > c.open else "bearish" if c.close < c.open else "doji"
            mark = "◄origin" if i == o else "◄KIRILIŞ" if i == b else ""
            L.append(f"  {i:>6} {c.open_time:%m-%d %H:%M}Z O{c.open} H{c.high} L{c.low} C{c.close} {col:<8}{mark}")
        L.append("-- her kopuş mumu adayı için algılama (pencere içi) --")
        for i in range(max(1, o), b + 1):
            g = pivot_zone(candles, i, pip, ze.p.draw_mode if ze.p.draw_mode in ("CANDLE", "PIVOT", "RANGE") else "RANGE")
            r = range_zone(candles, i, pip, ze.p.min_chain)
            L.append(f"  t={i} {_tstr(candles, i)}Z pivot: {'ZON ' + g.kind.value + ' [' + str(g.bottom) + '–' + str(g.top) + ']' if g else 'yok'} ← {explain_pivot(candles, i, pip)}")
            L.append(f"        range: {'ZON ' + r.kind.value + ' [' + str(r.bottom) + '–' + str(r.top) + ']' if r else 'yok'} ← {explain_range(candles, i, pip, ze.p.min_chain)}")
        L.append("-- penceredeki (ve yakın çevresindeki) tüm zonlar --")
        near = [z for z in ze.zones if o - 6 <= z.created_index <= b + 3]
        for z in near:
            in_win = o <= z.created_index <= b
            why = ("ADAY" if in_win and z.kind is kind else
                   "elendi: yön/tür uyumsuz" if in_win else
                   f"elendi: pencereden {'önce' if z.created_index < o else 'sonra'} doğdu")
            L.append(f"  [{why}] {zone_line(z, candles)}")
        if not near:
            L.append("  (yakın çevrede hiç zon yok)")
        linked = [z for z in ze.zones if any(x is e for x in z.caused_events)]
        L.append("-- sonuç: bu olaya bağlı zonlar: " + (", ".join(z.id for z in linked) if linked else "YOK → POI kurulumu oluşmaz"))
    if len(evs) > max_events:
        L.append(f"\n... {len(evs) - max_events} olay daha (kısaltıldı; --max-events ile artırın)")
    return "\n".join(L)
