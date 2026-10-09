"""Yapı motoru parametreleri — config'den; varsayılan yok."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..data.models import Timeframe


@dataclass(frozen=True)
class StructureParams:
    pip_size: Decimal
    min_pullback_pips: Decimal           # MS-R008 (parite × TF)
    threshold_inclusive: bool            # C-06 / D-16: True → ≥
    min_swing_candles: int               # C-05
    trend_change_confirmation: str = "SINGLE_BOS"   # MS-R014

    def __post_init__(self) -> None:
        if self.pip_size <= 0 or self.min_pullback_pips <= 0:
            raise ValueError("pip_size ve min_pullback_pips > 0 olmalı")
        if self.trend_change_confirmation != "SINGLE_BOS":
            # MS-R014 çift BOS: "HL ancak ikinci BOS ile kesinleşir" — mekanik tanım yok → Q-S05
            raise NotImplementedError("trend_change_confirmation=DOUBLE_BOS kodlanmadı (Q-S05)")

    @property
    def pipette(self) -> Decimal:
        """MS-R001: kırılım için asgari aşım = 0.1 pip."""
        return self.pip_size / 10

    @classmethod
    def from_config(cls, cfg, pair: str, tf: Timeframe) -> "StructureParams":
        cfg.require("structure_m1" if tf is Timeframe.M1 else "structure")
        return cls(cfg.pip_size(pair), cfg.swing_min_pullback_pips(pair, tf.value),
                   cfg.get("swing_threshold_inclusive"), cfg.get("min_swing_candles"),
                   cfg.get("trend_change_confirmation"))
