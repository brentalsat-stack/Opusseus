"""Pozisyon yönetimi planı (MG-R001, MG-R002, MG-R003, MG-R005; DECISIONS §5). Giriş anında çıkış planı belirlenir (MG-R005, L1).

Hacim dağılımı toplam hacmin yüzdesidir:
  PRO / MIXED (Q-P6: MIXED = pro-trend gibi): %20 @4R (risk kaldırma, stop yerinde) · %60 M15 zayıf swing · %20 4H zayıf swing
  COUNTER_HTF: %20 @4R · %80 ilk M15 hedefi (sonraki M15 S&D zonu / M15 swing)
  RANGE: %20 @4R · kalan hacmin tamamı range ucunda (otomatik sınıflama kaynakta yok → `range_extremes` verilirse, Q-M2)
Swing hedefi tutma onayı (D-26): son %20'yi 4H zayıf swing'e kadar tutmak için M15 hedefi dolduğunda 4H CHoCH (işlem yönünde,
girişten sonra) gerekir; yoksa M15 hedefinde kapatılır (Q-M1)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Mapping, Optional, Sequence, Union

from ..data.models import Timeframe
from ..risk.stops import Rejected, Side
from ..strategy.permission import TrendClass
from ..structure.models import EventType, MarketState, StructureEvent, Trend
from ..zones.models import Zone, ZoneKind

RISK_REMOVAL = "RISK_REMOVAL_4R"
M15_LEG = "M15_WEAK_SWING"
H4_LEG = "H4_WEAK_SWING"
CT_LEG = "FIRST_M15_TARGET"
RANGE_LEG = "RANGE_END"
HOLD_H4_CHOCH = "H4_CHOCH"


@dataclass(frozen=True)
class ManagementParams:
    removal_method: str            # PARTIAL (BE_AT_FIRST_EXEC_BOS: M1 swing BOS gerekir → kodlanmadı)
    partial_pct: Decimal           # 20
    partial_at_r: Decimal          # 4
    pt_m15_pct: Decimal            # 60
    pt_h4_pct: Decimal             # 20
    ct_pct: Decimal                # 80
    range_pct: Decimal             # 100 (risk kaldırma sonrası kalanın yüzdesi)
    swing_hold: str                # H4_CHOCH (D-26)
    second_target: str = "SWING_HI"   # PT'de son %20'nin hedefi: SWING_HI = "4H" rolünün zayıf swing'i (mevcut); NEXT_MID_ZONE = ilk hedefin ötesindeki en yakın orta-TF S&D zonu (V8, Q-V8-5)

    def __post_init__(self) -> None:
        if self.removal_method != "PARTIAL":
            raise NotImplementedError("risk_removal_method=BE_AT_FIRST_EXEC_BOS kodlanmadı: M1 swing BOS'u gerekir (Q-E4 ile aynı neden)")
        if self.partial_pct + self.pt_m15_pct + self.pt_h4_pct != 100:
            raise ValueError("pro-trend dağılımı toplam hacmin %100'ü olmalı (20+60+20)")
        if self.partial_pct + self.ct_pct != 100:
            raise ValueError("karşı-trend dağılımı toplam hacmin %100'ü olmalı (20+80)")
        if self.second_target not in ("SWING_HI", "NEXT_MID_ZONE"):
            raise ValueError(f"bilinmeyen management_second_target {self.second_target!r}")
        if self.swing_hold != "H4_CHOCH":
            raise NotImplementedError(f"swing_hold_confirmation={self.swing_hold} kodlanmadı (yalnız H4_CHOCH, D-26)")

    @classmethod
    def from_config(cls, cfg) -> "ManagementParams":
        cfg.require("management")
        d = lambda v: Decimal(str(v))
        ta = cfg.get("target_allocation")
        return cls(cfg.get("risk_removal_method"), d(cfg.get("partial_pct")), d(cfg.get("partial_at_r")),
                   d(ta["pro_trend"]["m15_weak_swing_pct"]), d(ta["pro_trend"]["h4_weak_swing_pct"]),
                   d(ta["counter_trend"]["allocation_pct"]), d(ta["range"]["allocation_pct"]), cfg.get("swing_hold_confirmation"),
                   cfg.get("management_second_target") or "SWING_HI")


@dataclass(frozen=True)
class Leg:
    name: str
    pct: Decimal                    # toplam hacmin %'si
    price: Decimal
    hold_requires: Optional[str] = None   # H4_LEG: M15 hedefi dolduğunda gereken onay (D-26)
    label: str = ""


@dataclass(frozen=True)
class TargetPlan:
    trend_class: str
    legs: tuple[Leg, ...]            # girişe yakından uzağa sıralı
    notes: tuple[str, ...] = ()

    @property
    def first_target(self) -> Optional[Leg]:
        """İptal kuralı için 'ilk hedef' (Q-E2): risk kaldırma bacağı hariç ilk bacak."""
        return next((l for l in self.legs if l.name != RISK_REMOVAL), None)


def first_target(side: Side, trend_class: Optional[TrendClass], entry: Decimal, states: Mapping[Timeframe, MarketState],
                 m15_zones: Sequence[Zone]) -> Optional[Decimal]:
    """İlk hedef (Q-E2): PRO/MIXED → M15 swing ucu (trend yönünde, girişin ötesinde); COUNTER_HTF → bir sonraki M15 S&D zonunun yakın
    kenarı veya M15 swing ucundan girişe en yakın olan. Yoksa None."""
    st = states.get(Timeframe.M15)
    cands: list[Decimal] = []
    long = side is Side.LONG
    if st is not None:
        pt = st.swing_high if long else st.swing_low
        if pt is not None and ((pt.price > entry) if long else (pt.price < entry)):
            cands.append(pt.price)
    if trend_class is TrendClass.COUNTER_HTF:
        for z in m15_zones:
            if z.valid and z.usable and z.kind is (ZoneKind.SUPPLY if long else ZoneKind.DEMAND):
                edge = z.bottom if long else z.top
                if (edge > entry) if long else (edge < entry):
                    cands.append(edge)
    if not cands:
        return None
    return min(cands) if long else max(cands)


def _swing_target(state: Optional[MarketState], side: Side, entry: Decimal) -> Optional[Decimal]:
    if state is None:
        return None
    pt = state.swing_high if side is Side.LONG else state.swing_low
    if pt is None:
        return None
    return pt.price if ((pt.price > entry) if side is Side.LONG else (pt.price < entry)) else None


def _next_zone_target(zones: Sequence[Zone], side: Side, beyond: Decimal) -> Optional[Decimal]:
    """V8 (Q-V8-5): ilk hedefin (`beyond`) ötesinde kalan, karşı yönlü (long için arz, short için talep) geçerli+kullanılabilir en yakın
    orta-TF S&D zonunun yakın kenarı. Yoksa None (son %20 ilk hedefe eklenir)."""
    long = side is Side.LONG
    edges = []
    for z in zones:
        if z.valid and z.usable and z.kind is (ZoneKind.SUPPLY if long else ZoneKind.DEMAND):
            edge = z.bottom if long else z.top
            if (edge > beyond) if long else (edge < beyond):
                edges.append(edge)
    return (min(edges) if long else max(edges)) if edges else None


def build_plan(side: Side, trend_class: Optional[TrendClass], entry: Decimal, stop: Decimal,
               states: Mapping[Timeframe, MarketState], m15_zones: Sequence[Zone], p: ManagementParams,
               range_extremes: Optional[tuple[Decimal, Decimal]] = None) -> Union[TargetPlan, Rejected]:
    """MG-R002 hedefleri + MG-R005 (çıkışı bilmiyorsan işlemde olma): M15/ilk hedef bulunamazsa NO_EXIT_PLAN reddi."""
    long = side is Side.LONG
    risk = abs(entry - stop)
    r_price = entry + p.partial_at_r * risk if long else entry - p.partial_at_r * risk
    legs = [Leg(RISK_REMOVAL, p.partial_pct, r_price, None, f"{p.partial_at_r}R")]
    notes: list[str] = []
    if range_extremes is not None:                                   # RANGE (Q-M2): yalnız açıkça verilirse
        tgt = range_extremes[1] if long else range_extremes[0]
        if not ((tgt > entry) if long else (tgt < entry)):
            return Rejected("NO_EXIT_PLAN", "MG-R005", "range ucu girişin ötesinde değil")
        legs.append(Leg(RANGE_LEG, (100 - p.partial_pct) * p.range_pct / 100, tgt, None, "range ucu"))
        cls = "RANGE"
    elif trend_class is TrendClass.COUNTER_HTF:
        tgt = first_target(side, trend_class, entry, states, m15_zones)
        if tgt is None:
            return Rejected("NO_EXIT_PLAN", "MG-R005", "ilk M15 hedefi (sonraki M15 S&D zonu / M15 swing) yok")
        legs.append(Leg(CT_LEG, p.ct_pct, tgt, None, "ilk M15 hedefi"))
        cls = TrendClass.COUNTER_HTF.value
    else:                                                            # PRO ve MIXED (Q-P6) aynı yönetilir
        m15 = _swing_target(states.get(Timeframe.M15), side, entry)
        if m15 is None:
            return Rejected("NO_EXIT_PLAN", "MG-R005", "M15 swing hedefi girişin ötesinde yok")
        if p.second_target == "NEXT_MID_ZONE":
            h4 = _next_zone_target(m15_zones, side, m15)
        else:
            h4 = _swing_target(states.get(Timeframe.H4), side, entry)
        if h4 is None:
            legs.append(Leg(M15_LEG, p.pt_m15_pct + p.pt_h4_pct, m15, None, "M15 zayıf swing"))
            notes.append("4H swing hedefi yok: %20 M15 hedefine eklendi")
        else:
            legs.append(Leg(M15_LEG, p.pt_m15_pct, m15, None, "M15 zayıf swing"))
            legs.append(Leg(H4_LEG, p.pt_h4_pct, h4, HOLD_H4_CHOCH, "4H zayıf swing"))
        cls = (trend_class.value if trend_class else "PRO")
    legs.sort(key=lambda l: l.price if long else -l.price)
    return TargetPlan(cls, tuple(legs), tuple(notes))


def split_lots(total: Decimal, pcts: Sequence[Decimal], step: Decimal, min_lot: Decimal) -> list[Decimal]:
    """Hacmi bacaklara böler: her bacak lot adımına AŞAĞI yuvarlanır, son bacak kalanı alır; min_lot'tan küçük bacaklar bir sonrakine
    eklenir (Q-M3: kaynakta kısmi kapamada min lot kuralı yok). Toplam korunur."""
    out = [((total * p / 100) / step).to_integral_value(rounding=ROUND_FLOOR) * step for p in pcts[:-1]]
    out.append(total - sum(out))
    for i in range(len(out) - 1):
        if out[i] < min_lot:
            out[i + 1] += out[i]
            out[i] = Decimal(0)
    if 0 < out[-1] < min_lot:
        j = max((i for i in range(len(out) - 1) if out[i] > 0), default=None)
        if j is not None:
            out[j] += out[-1]
            out[-1] = Decimal(0)
    return out


def h4_choch_since(h4_events: Sequence[StructureEvent], direction: Trend, since: datetime) -> bool:
    """D-26: girişten sonra işlem yönünde oluşan 4H CHoCH var mı (warm-up olayı değil)."""
    return any(e.type is EventType.CHOCH and e.dir is direction and not e.warmup and e.time > since for e in h4_events)
