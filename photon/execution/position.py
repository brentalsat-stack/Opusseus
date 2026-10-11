"""Pozisyon yöneticisi (MG-R001, MG-R003, MG-R004): bacak hedefleri, risk kaldırma (stop yerinde), scale-in kapısı.

Çıkış fiyatları spread'li: long bid ile (bid mumu), short ask ile (ask = bid + spread) çıkar. Aynı mumda stop ve hedef → STOP (DECISIONS §7,
tick yok): kalan hacmin tamamı stop'ta kapanır, durum sayılır. Hedef dolumları limit fiyatından; stop dolumu stop fiyatından, GAP'te açılış fiyatından.
Trailing yok; SL yalnızca BE için taşınabilir (MG-R003) — varsayılan yöntemde (PARTIAL) stop hiç taşınmaz."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from ..data.models import Candle
from ..risk.stops import Side
from .management import H4_LEG, M15_LEG, RISK_REMOVAL, Leg, ManagementParams, TargetPlan, split_lots


@dataclass(frozen=True)
class Fill:
    time: datetime
    leg: str                 # bacak adı | STOP | NO_HOLD_CONFIRMATION
    price: Decimal
    lots: Decimal
    r: Decimal               # bu dolumun R değeri (ilk riske göre)
    reason: str = ""


@dataclass
class Position:
    id: str
    side: Side
    entry: Decimal
    stop: Decimal
    lots_initial: Decimal
    lots_open: Decimal
    plan: TargetPlan
    leg_lots: dict[str, Decimal]
    opened_at: datetime
    fills: list[Fill] = field(default_factory=list)
    risk_removed: bool = False
    closed: bool = False
    notes: list[str] = field(default_factory=list)
    _filled_legs: set = field(default_factory=set)

    @property
    def risk(self) -> Decimal:
        return abs(self.entry - self.stop)

    @property
    def realized_r(self) -> Decimal:
        """Σ (lot_i / lot_ilk) × R_i  — T-MG-01: 0.2×4R + 0.8×(−1R) = 0."""
        return sum((f.lots / self.lots_initial * f.r for f in self.fills), Decimal(0))

    def pnl_amount(self, pip_size: Decimal, pip_value_per_lot: Decimal) -> Decimal:
        sign = 1 if self.side is Side.LONG else -1
        return sum((sign * (f.price - self.entry) / pip_size * f.lots * pip_value_per_lot for f in self.fills), Decimal(0))


@dataclass(frozen=True)
class ScaleInDecision:
    allowed: bool
    reason: str = ""
    rule: str = ""


class PositionManager:
    def __init__(self, params: ManagementParams, spread: Decimal, lot_step: Decimal, min_lot: Decimal):
        self.p, self.spread, self.lot_step, self.min_lot = params, spread, lot_step, min_lot
        self.stats = {"same_candle_stop_first": 0, "entry_and_stop_same_candle": 0, "stop_gap_fills": 0,
                      "entry_and_target_same_candle_ignored": 0}      # raporda gösterilir (DECISIONS §7, Aşama 7 kararları)

    def open(self, setup_id: str, side: Side, entry: Decimal, stop: Decimal, lots: Decimal, plan: TargetPlan,
             time: datetime) -> Position:
        lots_by_leg = split_lots(lots, [l.pct for l in plan.legs], self.lot_step, self.min_lot)
        return Position(setup_id, side, entry, stop, lots, lots, plan,
                        {l.name: q for l, q in zip(plan.legs, lots_by_leg)}, time)

    # ---- yardımcılar ----
    def _r(self, pos: Position, price: Decimal) -> Decimal:
        sign = 1 if pos.side is Side.LONG else -1
        return sign * (price - pos.entry) / pos.risk

    def _hit_stop(self, pos: Position, c: Candle) -> bool:
        return c.low <= pos.stop if pos.side is Side.LONG else c.high + self.spread >= pos.stop

    def _reached(self, pos: Position, leg: Leg, c: Candle) -> bool:
        return c.high >= leg.price if pos.side is Side.LONG else c.low + self.spread <= leg.price

    def _fill(self, pos: Position, time: datetime, name: str, price: Decimal, lots: Decimal, reason: str = "") -> Fill:
        f = Fill(time, name, price, lots, self._r(pos, price), reason)
        pos.fills.append(f)
        pos.lots_open -= lots
        return f

    def _stop_price(self, pos: Position, c: Candle, entry_candle: bool) -> Decimal:
        """Stop dolumu: stop fiyatından; GAP'te (mum açılışı stop'un ötesinde) açılış fiyatından (short: ask = bid + spread).
        Giriş mumunda açılış girişten önce olduğu için gap uygulanmaz."""
        if entry_candle:
            return pos.stop
        if pos.side is Side.LONG:
            return c.open if c.open < pos.stop else pos.stop
        ask_open = c.open + self.spread
        return ask_open if ask_open > pos.stop else pos.stop

    def on_candle(self, pos: Position, c: Candle, time: datetime, h4_choch_confirmed: bool = False,
                  entry_candle: bool = False) -> list[Fill]:
        """Bir M1 mumu: stop/hedef değerlendirmesi. `h4_choch_confirmed`: girişten sonra işlem yönünde 4H CHoCH var mı (D-26).
        `entry_candle`: pozisyonun dolduğu mum — mum içi sıra bilinmediğinden yalnızca STOP değerlendirilir (giriş + stop aynı mumda → stop;
        hedefler bu mumda yok sayılır, sayılır)."""
        if pos.closed:
            return []
        out: list[Fill] = []
        pending = [l for l in pos.plan.legs if l.name not in pos._filled_legs and pos.leg_lots.get(l.name, 0) > 0]
        reached = [l for l in pending if self._reached(pos, l, c)]
        if self._hit_stop(pos, c):
            if entry_candle:
                self.stats["entry_and_stop_same_candle"] += 1       # giriş + stop aynı mumda → giriş dolar ve stop olur (kötümser)
                pos.notes.append(f"ENTRY_AND_STOP_SAME_CANDLE@{time.isoformat()}")
            elif reached:
                self.stats["same_candle_stop_first"] += 1           # aynı mumda stop + hedef → stop (kötümser)
                pos.notes.append(f"SAME_CANDLE_STOP_FIRST@{time.isoformat()}")
            px = self._stop_price(pos, c, entry_candle)
            if px != pos.stop:
                self.stats["stop_gap_fills"] += 1
                pos.notes.append(f"STOP_GAP_FILL@{time.isoformat()}")
            if pos.lots_open > 0:
                out.append(self._fill(pos, time, "STOP", px, pos.lots_open,
                                      "SL_AFTER_RISK_REMOVAL" if pos.risk_removed else "SL"))
            pos.closed = True
            return out
        if entry_candle:
            if reached:
                self.stats["entry_and_target_same_candle_ignored"] += 1   # sıra bilinmiyor: hedefler bu mumda yok sayılır
                pos.notes.append(f"ENTRY_AND_TARGET_SAME_CANDLE_IGNORED@{time.isoformat()}")
            return out
        for leg in reached:                                            # girişe yakından uzağa
            if leg.name in pos._filled_legs:
                continue
            pos._filled_legs.add(leg.name)
            out.append(self._fill(pos, time, leg.name, leg.price, pos.leg_lots[leg.name]))
            if leg.name == RISK_REMOVAL:
                pos.risk_removed = True                                # stop yerinde (MG-R001)
            if leg.name == M15_LEG:                                    # D-26: 4H hedefine kadar tutma onayı
                h4 = next((l for l in pos.plan.legs if l.name == H4_LEG), None)
                if h4 is not None and h4.name not in pos._filled_legs and pos.leg_lots.get(H4_LEG, 0) > 0 and not h4_choch_confirmed:
                    pos._filled_legs.add(H4_LEG)
                    out.append(self._fill(pos, time, "NO_HOLD_CONFIRMATION", leg.price, pos.leg_lots[H4_LEG],
                                          "4H CHoCH onayı yok: son %20 M15 hedefinde kapatıldı"))
        if pos.lots_open <= 0:
            pos.closed = True
        return out

    def request_scale_in(self, pos: Position) -> ScaleInDecision:
        """MG-R004 (L1): scale-in yalnızca ilk pozisyonun riski kaldırıldıktan sonra (T-MG-02)."""
        if pos.closed:
            return ScaleInDecision(False, "POSITION_CLOSED", "MG-R004")
        if not pos.risk_removed:
            return ScaleInDecision(False, "RISK_NOT_REMOVED", "MG-R004")
        return ScaleInDecision(True)
