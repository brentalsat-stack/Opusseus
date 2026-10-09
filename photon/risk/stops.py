"""Stop ve giriş fiyatı (SL-R001..R003, SD-R008, EN-R009, FINAL_SPEC §8). Strateji kararı vermez; verilen zondan hesaplar."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Union


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class ZoneBounds:
    top: Decimal
    bottom: Decimal

    def __post_init__(self) -> None:
        if self.top <= self.bottom:
            raise ValueError("zone.top > zone.bottom olmalı")

    def distal(self, side: Side) -> Decimal:
        """Fiyatın ilk dokunduğu dış kenar: talepte (long) üst, arzda (short) alt."""
        return self.top if side is Side.LONG else self.bottom

    def extreme(self, side: Side) -> Decimal:
        """SL tarafındaki en uç fiyat: talepte alt, arzda üst."""
        return self.bottom if side is Side.LONG else self.top


@dataclass(frozen=True)
class EntryPlan:
    side: Side
    entry: Decimal
    stop: Decimal
    pip_risk: Decimal
    mode: str
    note: str = ""
    rules: tuple[str, ...] = ("SL-R001", "SL-R002", "SL-R003")


@dataclass(frozen=True)
class Rejected:
    reason: str
    rule: str
    detail: str = ""


@dataclass(frozen=True)
class StopParams:
    pip_size: Decimal
    entry_price_mode: str       # DISTAL | EQ | FIXED_SL
    fixed_sl_pips: Decimal
    sl_buffer_pips: Decimal
    min_sl_pips: Decimal

    @classmethod
    def from_config(cls, cfg, pair: str) -> "StopParams":
        cfg.require("risk_stops")
        mode = cfg.get("entry_price_mode")
        fixed = cfg.get("fixed_sl_pips")
        return cls(cfg.pip_size(pair), mode, Decimal(str(fixed if fixed is not None else 0)),
                   Decimal(str(cfg.get("sl_buffer_pips"))), Decimal(str(cfg.get("min_sl_pips"))))


def stop_price(zone: ZoneBounds, side: Side, p: StopParams) -> Decimal:
    """SL-R001: stop zonun en uç fiyatının 1 pipette ötesi (+ sl_buffer_pips; DECISIONS: ek pay 0)."""
    off = p.sl_buffer_pips * p.pip_size + p.pip_size / 10
    ext = zone.extreme(side)
    return ext - off if side is Side.LONG else ext + off


def plan_entry(zone: ZoneBounds, side: Side, p: StopParams) -> Union[EntryPlan, Rejected]:
    """Giriş ve stop (SD-R008, EN-R009). SL-R003: |giriş−stop| < min_sl_pips → ret (kaynakta 2. seçenek: girişi 2 pipe çekmek, IDR-06 — uygulanmadı).
    FIXED_SL: giriş = stop ± fixed_sl_pips; zon yüksekliği < fixed_sl_pips ise giriş = distal, stop = giriş ∓ fixed_sl_pips (DECISIONS)."""
    pip = p.pip_size
    note = ""
    if p.entry_price_mode == "DISTAL":
        entry, stop = zone.distal(side), stop_price(zone, side, p)
    elif p.entry_price_mode == "EQ":
        entry = ((zone.top + zone.bottom) / 2).quantize(pip / 10)
        stop = stop_price(zone, side, p)
    elif p.entry_price_mode == "FIXED_SL":
        if (zone.top - zone.bottom) / pip < p.fixed_sl_pips:
            entry = zone.distal(side)
            stop = entry - p.fixed_sl_pips * pip if side is Side.LONG else entry + p.fixed_sl_pips * pip
            note = "ZONE_SMALLER_THAN_FIXED_SL: entry=distal"
        else:
            stop = stop_price(zone, side, p)
            entry = stop + p.fixed_sl_pips * pip if side is Side.LONG else stop - p.fixed_sl_pips * pip
    else:
        raise ValueError(f"bilinmeyen entry_price_mode {p.entry_price_mode!r}")
    pip_risk = abs(entry - stop) / pip
    if pip_risk < p.min_sl_pips:
        return Rejected("SL_BELOW_MIN", "SL-R003", f"{pip_risk} pip < {p.min_sl_pips} pip")
    return EntryPlan(side, entry, stop, pip_risk, p.entry_price_mode, note)
