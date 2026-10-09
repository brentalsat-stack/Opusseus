"""Pozisyon büyüklüğü (FM-02, RK-R001, RK-R004, SL-R003). Daima aşağı yuvarlanır."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Union

from .stops import Rejected

MAX_RISK_PCT = Decimal("0.01")   # RK-R001: işlem başına risk asla %1'i aşmaz


@dataclass(frozen=True)
class SizingParams:
    pip_size: Decimal
    pip_value_per_lot: Decimal
    lot_step: Decimal
    min_lot: Decimal
    min_sl_pips: Decimal
    units_per_lot: Decimal
    risk_pct: Decimal

    def __post_init__(self) -> None:
        if not (Decimal(0) < self.risk_pct <= MAX_RISK_PCT):
            raise ValueError(f"risk_pct (0, 0.01] aralığında olmalı (RK-R001), alındı {self.risk_pct}")

    @classmethod
    def from_config(cls, cfg, pair: str, risk_pct: Decimal | None = None) -> "SizingParams":
        cfg.require("risk_sizing")
        pp = cfg.get(f"pair_params.{pair}")
        d = lambda v: Decimal(str(v))
        return cls(cfg.pip_size(pair), d(pp["pip_value_per_lot"]), d(pp["lot_step"]), d(pp["min_lot"]),
                   d(cfg.get("min_sl_pips")), d(pp["units_per_lot"]),
                   d(cfg.get("risk_pct")) if risk_pct is None else risk_pct)


@dataclass(frozen=True)
class SizeResult:
    lots: Decimal
    units: Decimal            # sinyalde lot yanında birim gösterimi
    risk_amount: Decimal      # balance × risk_pct (hedef)
    actual_risk: Decimal      # yuvarlanmış lotla gerçek risk (≤ risk_amount)
    pip_risk: Decimal


def position_size(balance: Decimal, entry: Decimal, stop: Decimal, p: SizingParams) -> Union[SizeResult, Rejected]:
    """FM-02: lots = floor_to_step(balance × risk_pct / (pip_risk × pip_value_per_lot))."""
    if balance <= 0 or entry <= 0 or stop <= 0 or entry == stop:
        return Rejected("INVALID_INPUT", "FM-02", f"balance={balance} entry={entry} stop={stop}")
    pip_risk = abs(entry - stop) / p.pip_size
    if pip_risk < p.min_sl_pips:
        return Rejected("SL_BELOW_MIN", "SL-R003", f"{pip_risk} pip < {p.min_sl_pips} pip")
    risk_amount = balance * p.risk_pct
    raw = risk_amount / (pip_risk * p.pip_value_per_lot)
    lots = (raw / p.lot_step).to_integral_value(rounding=ROUND_FLOOR) * p.lot_step   # RK-R004
    if lots < p.min_lot:
        return Rejected("LOT_BELOW_MIN", "FM-02", f"hesaplanan {lots} < min_lot {p.min_lot}")
    return SizeResult(lots, lots * p.units_per_lot, risk_amount, lots * pip_risk * p.pip_value_per_lot, pip_risk)
