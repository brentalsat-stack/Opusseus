"""Backtest motoru (Aşama 7; FINAL_SPEC §22). Sinyal + backtest: emirler yalnızca simüle edilir.

Dolum modeli (KULLANICI KARARLARI, Aşama 7):
  • Giriş limit emridir: long ask ≤ giriş (ask = bid + spread), short bid ≥ giriş ile dolar; dolum fiyatı = limit fiyatı (slipaj yok).
  • Stop: long bid ≤ stop, short ask ≥ stop; stop fiyatından, GAP'te (mum açılışı stop'un ötesinde) açılış fiyatından dolar.
  • Hedefler: long bid ≥ hedef, short ask ≤ hedef; hedef fiyatından dolar.
  • Aynı M1 mumunda giriş + stop → giriş dolar ve stop olur (kötümser); aynı mumda stop + hedef → stop (tick yok); sayılar raporlanır.
  • Mum içi yol yalnızca M1 OHLC'den; tick yok. Olay zamanı = olayın gerçekleştiği M1 mumunun AÇILIŞ zamanı.
Komisyon: IBKR (config costs.commission); değer yoksa 0 ile çalışır ve rapor "komisyon dahil değil" der.
Her dolum (giriş + her çıkış bacağı) ayrı emir sayılır: komisyon = max(min_per_order, tutar × rate_pct/100) (Q-B2)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from ..data.models import Candle, QuoteCandle, Timeframe
from ..execution.management import H4_LEG, M15_LEG, CT_LEG, RANGE_LEG, RISK_REMOVAL, ManagementParams, h4_choch_since
from ..execution.position import Fill, Position, PositionManager
from ..journal import journal_tag
from ..risk.stops import Side
from ..risk.sizing import SizingParams
from ..strategy.entry_model import OrderIntent, SignalEvent, fill_touch
from ..strategy.runner import StrategyRunner
from ..strategy.state_machine import Setup, State
from ..structure.models import Trend

log = logging.getLogger("photon.backtest")

FIRST_TARGET_LEGS = (M15_LEG, CT_LEG, RANGE_LEG)


@dataclass(frozen=True)
class CommissionModel:
    rate_pct: Decimal
    min_per_order: Decimal
    currency: str
    units_per_lot: Decimal
    included: bool = True

    @classmethod
    def from_config(cls, cfg, pair: str) -> "CommissionModel":
        """`costs.commission` yoksa/eksikse komisyon 0 ve `included=False` ("komisyon dahil değil")."""
        c = cfg.get("costs.commission")
        upl = Decimal(str(cfg.get(f"pair_params.{pair}.units_per_lot")))
        if not isinstance(c, dict) or c.get("rate_pct") is None or c.get("min_per_order") is None:
            return cls(Decimal(0), Decimal(0), cfg.get("account.currency") or "", upl, False)
        if c.get("model") != "PCT_OF_NOTIONAL":
            raise NotImplementedError(f"komisyon modeli {c.get('model')!r} kodlanmadı (yalnız PCT_OF_NOTIONAL)")
        if pair[3:] != cfg.get("account.currency"):
            raise NotImplementedError(f"komisyon tutarı kote para = hesap para birimi varsayar ({pair} / {cfg.get('account.currency')})")
        return cls(Decimal(str(c["rate_pct"])), Decimal(str(c["min_per_order"])), c.get("currency", ""), upl, True)

    def fee(self, lots: Decimal, price: Decimal) -> Decimal:
        if not self.included or lots <= 0:
            return Decimal(0)
        return max(self.min_per_order, lots * self.units_per_lot * price * self.rate_pct / 100)


@dataclass
class Trade:
    id: str
    setup: Setup
    intent: OrderIntent
    position: Position
    signal_time: datetime
    fill_time: datetime
    close_time: Optional[datetime] = None
    commission: Decimal = Decimal(0)
    gross_pnl: Decimal = Decimal(0)
    balance_before: Decimal = Decimal(0)
    balance_after: Decimal = Decimal(0)
    open: bool = True

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.commission

    @property
    def r_gross(self) -> Decimal:
        return self.position.realized_r

    @property
    def r_net(self) -> Decimal:
        """Komisyon dahil R: net PnL / işlemin hedef risk tutarı."""
        ra = self.intent.risk_amount
        return self.net_pnl / ra if ra else Decimal(0)

    @property
    def win(self) -> bool:
        return self.net_pnl > 0

    @property
    def outcome(self) -> str:
        return "WIN" if self.win else "LOSS"

    @property
    def journal_tag(self) -> str:
        """FINAL_SPEC §24 Trade.journal_tag. Backtest'te yalnızca plana uygun (kapıları geçmiş) işlem açılır → daima VALID (Q-B3)."""
        return journal_tag(True, self.win)

    def target_r(self, leg_names: tuple[str, ...]) -> Optional[Decimal]:
        long = self.intent.side is Side.LONG
        risk = abs(self.intent.entry - self.intent.stop)
        for l in self.intent.plan.legs:
            if l.name in leg_names:
                return ((l.price - self.intent.entry) if long else (self.intent.entry - l.price)) / risk
        return None

    @property
    def m15_target_r(self) -> Optional[Decimal]:
        """M15/ilk hedefin R uzaklığı (Q-M5 raporu: 4R'den yakın mı?)."""
        return self.target_r(FIRST_TARGET_LEGS)


@dataclass
class BacktestResult:
    pair: str
    start: datetime
    end: datetime
    initial_balance: Decimal
    final_balance: Decimal
    trades: list[Trade]
    open_trades: list[Trade]
    events: list[SignalEvent]
    commission: CommissionModel
    fill_stats: dict
    limit_report: dict
    unfilled_orders: int
    candles: int
    equity: list[tuple[datetime, Decimal]] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, cfg, pair: str, start: datetime, end: datetime, initial_balance: Decimal, news=None, publisher=None):
        cfg.require("backtest", "strategy", "management")
        self.cfg, self.pair, self.start, self.end = cfg, pair, start, end
        self.initial = initial_balance
        self.runner = StrategyRunner(cfg, pair, start, initial_balance, news, publisher)
        self.model = self.runner.model
        sz = SizingParams.from_config(cfg, pair)
        self.pip = cfg.pip_size(pair)
        self.pip_value = sz.pip_value_per_lot
        self.spread = self.model.p.spread
        self.pm = PositionManager(ManagementParams.from_config(cfg), self.spread, sz.lot_step, sz.min_lot)
        self.commission = CommissionModel.from_config(cfg, pair)
        self.pending: dict[str, Setup] = {}
        self.positions: dict[str, Trade] = {}
        self.closed: list[Trade] = []
        self.events: list[SignalEvent] = []
        self.equity: list[tuple[datetime, Decimal]] = []
        self.n_candles = 0

    # ---- mum başı simülasyon (giriş modeli adımından ÖNCE) ----
    def _pre_step(self, c: Candle) -> None:
        self.n_candles += 1
        now = c.open_time
        for sid, s in list(self.pending.items()):
            if s.state is not State.ORDER_PENDING:                  # iptal/yerine koyma: izleme dışı
                del self.pending[sid]
                continue
            it: OrderIntent = s.intent
            if not fill_touch(it.side, it.entry, c, self.spread):
                continue
            del self.pending[sid]
            self._fill_entry(s, it, c, now)
        for sid, tr in list(self.positions.items()):
            if tr.fill_time == now:                                  # bu mumda yeni doldu: giriş mumu kuralları _fill_entry'de uygulandı
                continue
            self._manage(tr, c, now, entry_candle=False)

    def _fill_entry(self, s: Setup, it: OrderIntent, c: Candle, now: datetime) -> None:
        pos = self.pm.open(s.id, it.side, it.entry, it.stop, it.lots, it.plan, now)
        tr = Trade(s.id, s, it, pos, it.time, now, balance_before=self.runner.balance)
        tr.commission += self.commission.fee(it.lots, it.entry)
        self.model.mark_filled(s, now)
        self.positions[s.id] = tr
        self._manage(tr, c, now, entry_candle=True)

    def _manage(self, tr: Trade, c: Candle, now: datetime, entry_candle: bool) -> None:
        pos, it = tr.position, tr.intent
        direction = Trend.BULL if it.side is Side.LONG else Trend.BEAR
        h4_ok = False
        if not entry_candle and any(l.name == H4_LEG and l.name not in pos._filled_legs for l in pos.plan.legs):
            h4_ok = h4_choch_since(self.runner.struct[Timeframe.H4].events, direction, pos.opened_at)
        fills = self.pm.on_candle(pos, c, now, h4_choch_confirmed=h4_ok, entry_candle=entry_candle)
        for f in fills:
            tr.commission += self.commission.fee(f.lots, f.price)
        if pos.risk_removed and tr.setup.state is State.POSITION_OPEN:
            self.model.mark_risk_free(tr.setup, now)                # MG-R001 → MG-R004 scale-in kapısı açılır
        if pos.closed:
            self._close(tr, now)

    def _close(self, tr: Trade, now: datetime) -> None:
        tr.open = False
        tr.close_time = now
        tr.gross_pnl = tr.position.pnl_amount(self.pip, self.pip_value)
        self.runner.balance += tr.net_pnl                             # bileşik büyüme: sonraki sinyaller güncel bakiyeyle boyutlanır
        tr.balance_after = self.runner.balance
        self.model.mark_closed(tr.setup, now, tr.net_pnl)             # RK-R003: kayıp sayacı net PnL ile (Q-P3)
        del self.positions[tr.id]
        self.closed.append(tr)
        self.equity.append((now, tr.balance_after))
        log.info("%s kapandı: %s R=%.2f net=%.2f bakiye=%.2f", tr.id, tr.outcome, tr.r_gross, tr.net_pnl, tr.balance_after)

    # ---- ana döngü ----
    def run(self, m1: list[QuoteCandle]) -> BacktestResult:
        for q in m1:
            evs = self.runner.on_m1(q, pre_step=self._pre_step)
            for e in evs:
                self.events.append(e)
                if e.kind == "SIGNAL":
                    self.pending[e.setup.id] = e.setup
                elif e.kind == "CANCELLED":
                    self.pending.pop(e.setup.id, None)
        return BacktestResult(self.pair, self.start, self.end, self.initial, self.runner.balance, self.closed,
                              list(self.positions.values()), self.events, self.commission,
                              dict(self.pm.stats), self.runner.limit_report(), len(self.pending), self.n_candles, self.equity)
