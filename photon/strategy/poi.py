"""POI kapıları + puanlama (DECISIONS v2.0 §3, POI-R004, POI-R002; kullanıcı plan katmanı). Eşik puan YOK:
kapıları geçen her POI'de sinyal üretilir; puan ve kriter dökümü sinyale yazılır.

Zorunlu kapılar: POI ≥ M15 · SD-R005 (structure/flip) · PD-R003 range filtresi · EN-R006 izin · seans · liquidation.
Ağırlıklı 10 kriter: config `poi_scoring.weights`. Bilinmeyen kriter (None) puan almaz ve dökümde 'bilinmiyor' görünür."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from ..data.models import Timeframe
from ..liquidity.liquidation import LiquidationResult
from ..risk.session import Decision
from ..structure import pd as PD
from ..structure.models import MarketState, Trend
from ..zones.models import Origin, Zone
from .permission import Permission, TrendClass, classify_trend

CRITERIA = ("bos_and_flip", "swing_break", "nested_zone", "pro_trend", "sweep_zone",
            "inducement", "pivot_zone", "weak_target", "pd_alignment", "corrective_or_vshape")
_RULES = {"bos_and_flip": "SD-R005/R007", "swing_break": "SD-R005", "nested_zone": "POI-R002#6", "pro_trend": "EN-R006",
          "sweep_zone": "LQ-R002", "inducement": "LQ-R003", "pivot_zone": "POI-R002#7", "weak_target": "POI-R002#9",
          "pd_alignment": "PD-R001", "corrective_or_vshape": "LQ-R006/EN-R001"}


@dataclass(frozen=True)
class POIParams:
    weights: Mapping[str, Decimal]
    range_filter_enabled: bool
    range_band_pct: Decimal
    range_tf: Timeframe
    require_liquidation: bool

    def __post_init__(self) -> None:
        missing = [k for k in CRITERIA if k not in self.weights]
        if missing:
            raise ValueError(f"poi_scoring.weights eksik: {missing}")

    @classmethod
    def from_config(cls, cfg) -> "POIParams":
        cfg.require("poi_scoring", "liquidity")
        w = {k: Decimal(str(v)) for k, v in cfg.get("poi_scoring.weights").items()}
        return cls(w, cfg.get("range_extreme_filter.enabled"), Decimal(str(cfg.get("range_extreme_filter.allowed_band_pct"))),
                   Timeframe(cfg.get("range_extreme_filter.range_tf")), cfg.get("require_liquidation"))


@dataclass(frozen=True)
class POIContext:
    direction: Trend                                   # işlem yönü (BULL=long)
    states: Mapping[Timeframe, MarketState]            # en az M15 ve H4
    permission: Permission                             # EN-R006 (çağıran hesaplar)
    session: Decision                                  # SS-R001/R002
    liquidation: Optional[LiquidationResult] = None    # sinyal anında (M1)
    has_inducement: Optional[bool] = None              # alarm anında hesaplanmış (LQ-R003)
    nested_parents: Sequence[Zone] = ()                # 4H/D zonlar (refine.nested_parents)
    v_shape: Optional[bool] = None                     # V-shape çıkış (Q-Z8); None = ölçüt/veri yok


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    reason: str
    rule: str


@dataclass(frozen=True)
class Criterion:
    name: str
    weight: Decimal
    earned: Optional[bool]       # None = bilinmiyor (puan yok)
    rule: str

    @property
    def points(self) -> Decimal:
        return self.weight if self.earned else Decimal(0)


@dataclass(frozen=True)
class POIResult:
    zone: Zone
    gates: tuple[Gate, ...]
    criteria: tuple[Criterion, ...]

    @property
    def passed(self) -> bool:
        return all(g.passed for g in self.gates)

    @property
    def failed_gates(self) -> list[Gate]:
        return [g for g in self.gates if not g.passed]

    @property
    def score(self) -> Decimal:
        return sum((c.points for c in self.criteria), Decimal(0))

    @property
    def max_score(self) -> Decimal:
        return sum((c.weight for c in self.criteria), Decimal(0))

    def breakdown(self) -> str:
        return "; ".join(f"{c.name}={'+' + str(c.weight) if c.earned else ('?' if c.earned is None else '0')}"
                         for c in self.criteria)


def _gates(z: Zone, ctx: POIContext, p: POIParams) -> tuple[Gate, ...]:
    out = [Gate("tf_min_m15", z.tf.delta >= Timeframe.M15.delta, "" if z.tf.delta >= Timeframe.M15.delta else f"{z.tf.value} < M15",
                "POI-R004#1"),
           Gate("structure_or_flip", z.valid, "" if z.valid else "zon yapı kırılımına neden olmadı ve flip değil", "SD-R005")]
    if p.range_filter_enabled:
        st = ctx.states.get(p.range_tf)
        if st is None:
            out.append(Gate("range_filter", False, f"RANGE_STATE_MISSING({p.range_tf.value})", "PD-R003"))
        else:
            r = PD.range_filter(ctx.direction, z.eq, st, p.range_band_pct)
            out.append(Gate("range_filter", r.passed, r.reason + (f" ({r.position_pct:.1f}%)" if r.position_pct is not None else ""),
                            "PD-R003"))
    else:
        out.append(Gate("range_filter", True, "DISABLED", "PD-R003"))
    out.append(Gate("permission", ctx.permission.allowed, ctx.permission.reason if not ctx.permission.allowed else ctx.permission.row,
                    "EN-R006"))
    out.append(Gate("session", ctx.session.allowed, ctx.session.reason, ctx.session.rule or "SS-R001"))
    if p.require_liquidation:
        liq = ctx.liquidation
        ok = liq is not None and liq.found
        out.append(Gate("liquidation", ok, "" if ok else (liq.reason if liq else "NOT_EVALUATED"), "EN-R001/1"))
    else:
        out.append(Gate("liquidation", True, "DISABLED", "EN-R001/1"))
    return tuple(out)


def _pd_both(z: Zone, ctx: POIContext) -> Optional[bool]:
    vals = []
    for tf in (Timeframe.M15, Timeframe.H4):
        st = ctx.states.get(tf)
        vals.append(None if st is None else PD.aligned(ctx.direction, PD.classify_state(st, z.eq)))
    if any(v is None for v in vals):
        return None
    return all(vals)


def _weak_target(ctx: POIContext) -> Optional[bool]:
    trends = [ctx.states[tf].swing_trend for tf in (Timeframe.M15, Timeframe.H4) if tf in ctx.states]
    if not trends or all(t is Trend.UNDEFINED for t in trends):
        return None
    return any(t is ctx.direction for t in trends)       # trend yönünde zayıf (hedeflenecek) uç var


def _pro_trend(ctx: POIContext) -> Optional[bool]:
    a, b = ctx.states.get(Timeframe.H4), ctx.states.get(Timeframe.M15)
    if a is None or b is None or Trend.UNDEFINED in (a.swing_trend, b.swing_trend):
        return None
    return classify_trend(a.swing_trend, b.swing_trend, ctx.direction) is TrendClass.PRO


def evaluate_poi(z: Zone, ctx: POIContext, p: POIParams) -> POIResult:
    earned = {
        "bos_and_flip": bool(z.is_flip and z.caused_events),
        "swing_break": z.caused_swing_bos,
        "nested_zone": bool(ctx.nested_parents) and z.tf is Timeframe.M15,
        "pro_trend": _pro_trend(ctx),
        "sweep_zone": z.is_sweep,
        "inducement": ctx.has_inducement,
        "pivot_zone": z.origin is Origin.PIVOT,
        "weak_target": _weak_target(ctx),
        "pd_alignment": _pd_both(z, ctx),
        "corrective_or_vshape": ctx.v_shape,
    }
    crit = tuple(Criterion(k, p.weights[k], earned[k], _RULES[k]) for k in CRITERIA)
    return POIResult(z, _gates(z, ctx, p), crit)
