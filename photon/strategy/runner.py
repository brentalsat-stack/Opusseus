"""Çok-zaman-dilimli çalıştırıcı: M1 bid/ask akışı → D1/H4/M15 mumları → yapı + zon motorları → POI kurulumları → giriş modeli.
Backtest ve canlı sinyal için ortak çekirdek (FINAL_SPEC §18, §22: aynı anda kapanan mumlarda HTF → LTF sırası).

Her M1 mumu kapandığında: (1) kapanan HTF mumları D1→H4→M15 sırasıyla motorlara verilir, (2) M1 iç-yapı + zon motorları güncellenir,
(3) giriş modeli adımlanır. Yalnızca kapanmış mumlar kullanılır; warm-up süresince (live_from öncesi) kurulumlar ilerlemez (Q-S01)."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from ..data.models import Candle, PriceSide, QuoteCandle, Timeframe
from ..data.resample import BoundarySpec, bin_bounds
from ..data.resolver import SubTfResolver
from ..data.models import OHLC
from ..risk.limits import DayLossTracker
from ..risk.session import SessionClock
from ..risk.sizing import SizingParams
from ..risk.stops import StopParams
from ..signals.news import NewsCalendar
from ..structure.engine import StructureEngine
from ..structure.models import EventType, StructureEvent
from ..structure.params import StructureParams
from ..zones.engine import ZoneEngine, ZoneParams
from ..execution.management import ManagementParams
from .entry_model import EntryModel, EntryParams, MarketView, SignalEvent
from .poi import POIParams

HTF = (Timeframe.D1, Timeframe.H4, Timeframe.M15)
M1_ZONE_RETIRE_CANDLES = 1440   # uygulama sınırı (Q-L3): M1 zonları 1 günden eskiyse izlenmez (entry zonu yakın CHoCH bacağındandır)


class MtfAggregator:
    """M1 → D1/H4/M15 (bid ve ask OHLC). Bir kutu, son M1'i geldiğinde veya sonraki kutuya geçildiğinde (hafta sonu boşluğu) kapanır."""

    def __init__(self, spec: BoundarySpec):
        self.spec = spec
        self._cur: dict[Timeframe, Optional[dict]] = {tf: None for tf in HTF}

    @staticmethod
    def _close(tf: Timeframe, a: dict) -> QuoteCandle:
        b, k = a["b"], a["a"]
        return QuoteCandle(a["pair"], tf, a["start"], OHLC(b[0], b[1], b[2], b[3]), OHLC(k[0], k[1], k[2], k[3]), True, None)

    def feed(self, c: QuoteCandle) -> list[QuoteCandle]:
        out: list[QuoteCandle] = []
        for tf in HTF:                                   # HTF → LTF sırası
            cur = self._cur[tf]
            if cur is not None and cur["start"] <= c.open_time < cur["end"]:
                start, end = cur["start"], cur["end"]            # aynı kutu: sınırları yeniden hesaplama
            else:
                start, end = bin_bounds(c.open_time, tf, self.spec)
                if cur is not None and cur["start"] != start:    # boşluk: önceki kutu tamamlandı
                    out.append(self._close(tf, cur))
                    cur = None
            if cur is None:
                cur = {"pair": c.pair, "start": start, "end": end,
                       "b": [c.bid.open, c.bid.high, c.bid.low, c.bid.close],
                       "a": [c.ask.open, c.ask.high, c.ask.low, c.ask.close]}
            else:
                for key, o in (("b", c.bid), ("a", c.ask)):
                    arr = cur[key]
                    arr[1], arr[2], arr[3] = max(arr[1], o.high), min(arr[2], o.low), o.close
            self._cur[tf] = cur
            if c.open_time + c.tf.delta >= end:              # kutunun son M1'i
                out.append(self._close(tf, cur))
                self._cur[tf] = None
        return out


class StrategyRunner:
    def __init__(self, cfg, pair: str, live_from: datetime, balance: Decimal,
                 news: Optional[NewsCalendar] = None, publisher=None):
        cfg.require("strategy", "data_boundaries", "structure_warmup")
        self.publisher = publisher                 # signals.output.SignalPublisher (isteğe bağlı): olaylar ekrana/log'a yazılır
        self.pair, self.live_from, self.balance = pair, live_from, balance
        self.side = PriceSide(cfg.get("candle_price_side"))
        self.agg = MtfAggregator(BoundarySpec.from_config(cfg))
        self._q: list[QuoteCandle] = []
        self._qt: list[datetime] = []
        res = SubTfResolver(self._q, self.side, times=self._qt)          # Q-S04: HTF outside bar → M1 (tick yok → çözülemezse OUTSIDE_BAR)
        pip = cfg.pip_size(pair)
        self.struct: dict[Timeframe, StructureEngine] = {}
        self.zones_eng: dict[Timeframe, ZoneEngine] = {}
        for tf in HTF:
            st = StructureEngine(tf, StructureParams.from_config(cfg, pair, tf), res, live_from)
            st.start_auto()
            self.struct[tf] = st
            self.zones_eng[tf] = ZoneEngine(tf, ZoneParams.from_config(cfg, pair, tf), st)
        self.m1_struct = StructureEngine(Timeframe.M1, StructureParams.internal_only_params(pip), None, live_from)
        zp1 = ZoneParams.from_config(cfg, pair, Timeframe.M1)
        self.m1_zones = ZoneEngine(Timeframe.M1, ZoneParams(zp1.pip_size, zp1.draw_mode, zp1.min_chain, zp1.reaction_min_pips,
                                                            zp1.eqh_tol_pips, M1_ZONE_RETIRE_CANDLES), self.m1_struct)
        self.m1: list[Candle] = []
        self.m15_events: list[StructureEvent] = []
        self.zone_lists = {tf: self.zones_eng[tf].zones for tf in HTF}
        self.model = EntryModel(pair, EntryParams.from_config(cfg, pair), POIParams.from_config(cfg), StopParams.from_config(cfg, pair),
                                SizingParams.from_config(cfg, pair), SessionClock.from_config(cfg),
                                DayLossTracker.from_config(cfg), ManagementParams.from_config(cfg), news)
        self._watched: set[str] = set()
        self._states: dict[Timeframe, object] = {}

    def limit_report(self) -> dict:
        """Q-L3 uygulama sınırları yüzünden elenen/etkilenen durumların sayısı (backtest raporu için)."""
        rep = dict(self.model.stats)
        for name, ze in [("m1", self.m1_zones)] + [(tf.value, self.zones_eng[tf]) for tf in HTF]:
            for k, v in ze.limits.items():
                rep[f"zones_{name}_{k}"] = v
        return rep

    @property
    def live(self) -> bool:
        return bool(self.m1) and self.m1[-1].open_time >= self.live_from

    def on_m1(self, qc: QuoteCandle) -> list[SignalEvent]:
        """Bir M1 (bid/ask) mumu kapandı → sinyal/iptal/ret olayları."""
        self._q.append(qc)
        self._qt.append(qc.open_time)
        c = qc.to_candle(self.side)
        self.m1.append(c)
        htf = self.agg.feed(qc)
        for hq in htf:
            hc = hq.to_candle(self.side)
            st, ze = self.struct[hq.tf], self.zones_eng[hq.tf]
            ev = st.update(hc)
            ze.update(hc, ev)
            if hq.tf is Timeframe.M15:
                self.m15_events.extend(e for e in ev if e.type in (EventType.BOS, EventType.CHOCH))
            for z in ze.validated:                          # SD-R005: geçerli olan her ≥M15 zon için POI kurulumu
                if z.id not in self._watched and z.usable:
                    self._watched.add(z.id)
                    self.model.watch(z, ze, self.zone_lists)
            ze.validated.clear()
        ev1 = self.m1_struct.update(c)
        self.m1_zones.update(c, ev1)
        if htf or not self._states:                           # durum yalnızca HTF mumu kapanınca değişir
            self._states = {tf: self.struct[tf].state() for tf in (Timeframe.H4, Timeframe.M15)}
        states = self._states
        view = MarketView(c.open_time + qc.tf.delta, self.m1, len(self.m1) - 1, ev1, self.m1_struct, self.m1_zones,
                          states, self.m15_events, self.zone_lists, self.balance)
        events = self.model.step(view, live=self.live)
        if self.publisher is not None:
            for e in events:
                self.publisher.publish(e)
        return events
