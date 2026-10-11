"""Giriş modeli (EN-R001, EN-R002, EN-R006..R009; FINAL_SPEC §8, §17). Sinyal + backtest: emri kullanıcı girer.

CONFIRMATION akışı (DECISIONS §4):  WATCHING → [POI/rafine zon mitigasyonu] → POI_MITIGATED → [EN-R006 izni + karşı-HTF çift BOS]
  → CONFIRMATION_PENDING → [M1 CHoCH (mitigasyondan SONRA)] → ENTRY_READY → [flip zonu, yoksa extreme; kapılar; SL; boyut]
  → ORDER_PENDING (limit sinyal) → [ilk hedefe dolmadan ulaşılırsa iptal → WATCHING].
RISK akışı: HTF POI'ye doğrudan limit (LTF onayı yok; liquidation kapısı uygulanamaz — Q-E3).  DOUBLE_CONFIRMATION: kodlanmadı (Q-E4).
Fiyat/karar girdileri `MarketView` ile verilir (motorlar dışarıda); bu modül yalnızca karar mantığıdır.
"""
from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Mapping, Optional, Sequence, Union

from ..data.models import Candle, Timeframe
from ..execution.management import ManagementParams, TargetPlan, build_plan, first_target, split_lots  # noqa: F401  (first_target: geriye dönük içe aktarım)
from ..liquidity import internal_levels, liquidation, v_shape_exit
from ..liquidity.liquidation import MAX_WINDOW
from ..risk.limits import DayLossTracker
from ..risk.session import SessionClock
from ..risk.sizing import SizeResult, SizingParams, position_size
from ..risk.stops import EntryPlan, Rejected, Side, StopParams, ZoneBounds, plan_entry
from ..signals.news import NewsCalendar, NewsNote, NewsStatus
from ..structure.engine import StructureEngine
from ..structure.pd import swing_range
from ..structure.models import EventType, MarketState, StructureEvent, Trend
from ..zones.engine import ZoneEngine
from ..zones.models import Origin, Zone, ZoneKind
from ..zones.refine import nested_parents, refined_zones
from .permission import TrendClass, check_permission, classify_trend, m15_choch_after_mitigation
from .poi import POIContext, POIParams, POIResult, evaluate_poi
from .state_machine import ACTIVE_ORDER_STATES, Setup, State

log = logging.getLogger(__name__)
M1 = Timeframe.M1


@dataclass(frozen=True)
class EntryParams:
    entry_type: str                       # CONFIRMATION | RISK (DOUBLE_CONFIRMATION → NotImplementedError, Q-E4)
    decisional_flip_requires_sweep: bool  # D-06 / EN-R008
    counter_htf_require_double_bos: bool  # D-15 / EN-R007
    require_refined_ltf_zone: bool        # D-02
    duplicate_policy: str                 # REJECT | REPLACE | ALLOW (Q-E5)
    opposite_policy: str                  # REJECT | ALLOW (Q-E6)
    v_shape_max_candles: int              # Q-Z8
    eq_tol: Decimal                       # eşit tepe/dip toleransı (fiyat)
    pipette: Decimal
    spread: Decimal                       # sabit spread (fiyat): ask = bid + spread
    refine_min_tf: Timeframe = Timeframe.H4   # D-02 / "4H POI" rolü (profil: M1→H4, V8→D1)
    min_refine_pips: Decimal = Decimal(0)     # V8 [00:34:45]: POI bu yükseklikten (pip) küçükse rafine edilmez; 0 = kapalı (mevcut davranış)
    entry_zone_choice: str = "FLIP_FIRST"  # FLIP_FIRST (varsayılan; EN-R008, config'te anahtar yok) | EXTREME_ALWAYS (varyant testi: EN-R008 C-11 seçeneği — flip yerine hep V tepki kutusu)

    def __post_init__(self) -> None:
        if self.entry_type == "DOUBLE_CONFIRMATION":
            raise NotImplementedError("DOUBLE_CONFIRMATION kodlanmadı: M1 swing BOS'u gerekir, M1 swing eşiği henüz yok (Q-E4)")
        if self.entry_zone_choice not in ("FLIP_FIRST", "EXTREME_ALWAYS"):
            raise ValueError(f"bilinmeyen entry_zone_choice {self.entry_zone_choice!r}")
        if self.entry_type not in ("CONFIRMATION", "RISK"):
            raise ValueError(f"bilinmeyen entry_type {self.entry_type!r}")

    @classmethod
    def from_config(cls, cfg, pair: str) -> "EntryParams":
        from .profile import profile_from_config
        cfg.require("strategy")
        pip = cfg.pip_size(pair)
        prof = profile_from_config(cfg)
        return cls(cfg.get("entry_type"), cfg.get("decisional_flip_requires_sweep"),
                   cfg.get("counter_htf_require_double_bos"), cfg.get("require_refined_ltf_zone_in_htf_poi"),
                   cfg.get("duplicate_signal_policy"), cfg.get("opposite_signal_policy"),
                   cfg.get("v_shape_metric.max_candles"), Decimal(str(cfg.get("eqh_tolerance.pips"))) * pip, pip / 10,
                   Decimal(str(cfg.get("costs.spread_pips"))) * pip, prof.refine_min_tf,
                   Decimal(str(cfg.get("min_refine_pips") or 0)), cfg.get("entry_zone_choice") or "FLIP_FIRST")


@dataclass
class MarketView:
    """Bir M1 mumu kapandığındaki piyasa görünümü (motorlar çağıran tarafından güncellenmiştir)."""
    now: datetime                                   # M1 mumunun KAPANIŞ anı (UTC)
    m1: Sequence[Candle]                            # bid M1 mumları; m1[i] = bu mum
    i: int
    m1_events: Sequence[StructureEvent]             # bu mumda M1 iç-yapı motorunun ürettiği olaylar
    m1_struct: StructureEngine                      # internal_only
    m1_zones: ZoneEngine
    states: Mapping[Timeframe, MarketState]         # en az H4, M15
    m15_events: Sequence[StructureEvent]
    zones: Mapping[Timeframe, Sequence[Zone]]       # D1/H4/M15 zon listeleri
    balance: Decimal


@dataclass(frozen=True)
class OrderIntent:
    setup_id: str
    pair: str
    side: Side
    type: str                                        # LIMIT
    entry: Decimal
    stop: Decimal
    pip_risk: Decimal
    lots: Decimal
    units: Decimal
    risk_pct: Decimal
    risk_amount: Decimal
    time: datetime
    poi_id: str
    poi_tf: Timeframe
    entry_zone_id: str
    entry_zone_kind: str                             # FLIP | EXTREME | POI
    cancel_if_reaches: Optional[Decimal]             # ilk hedef: dolmadan bu fiyata ulaşılırsa iptal
    plan: TargetPlan                                 # MG-R002/R005: giriş anında belirlenen çıkış planı
    leg_lots: tuple[Decimal, ...]                    # bacak başına GERÇEKLEŞEN lot (lot adımı yuvarlaması sonrası; Q-M3)
    criteria: tuple[tuple[str, Decimal, Optional[bool]], ...]   # POI kriterleri: (ad, ağırlık, kazanıldı mı / None=bilinmiyor)
    h4_trend: str
    m15_trend: str
    session: str
    trend_class: str
    poi_score: Decimal
    poi_max_score: Decimal
    score_breakdown: str
    shares_event_with: tuple[str, ...]
    news: str
    rules: tuple[str, ...]
    choch_gap: Optional[int] = None                  # sinyal anında: POI'ye dokunuştan M1 CHoCH'a mum sayısı (V-shape N karşılaştırması için; kurulum sonradan yeniden kullanılır)


@dataclass(frozen=True)
class SignalEvent:
    kind: str                                        # SIGNAL | CANCELLED | REJECTED
    setup: Setup
    time: datetime
    intent: Optional[OrderIntent] = None
    reason: str = ""


# ------------------------------------------------------------------ yardımcılar
def _window_zones(ze: ZoneEngine, choch: StructureEvent) -> str:
    """NO_ENTRY_ZONE teşhisi: CHoCH penceresinde [origin, break] doğan M1 zonları (yön fark etmeksizin) ve pencere uzunluğu.
    `retire_after` hipotezi: pencere uzunluğu > retire_after ise emekli zon bağlamayı etkileyebilirdi (`leg_len`)."""
    want = ZoneKind.DEMAND if choch.dir is Trend.BULL else ZoneKind.SUPPLY
    inw = [z for z in ze.zones if choch.origin_index <= z.created_index <= choch.break_index]
    same = [z for z in inw if z.kind is want]
    return (f"retire_after={ze.p.retire_after} leg_len={choch.break_index - choch.origin_index} "
            f"zones_in_window={len(inw)} same_kind={len(same)} "
            f"same_kind_detail=[{', '.join(f'{z.id}:{z.origin.value}:valid={z.valid}:flip={z.is_flip}:caused={len(z.caused_events)}' for z in same)}]")


def _range_detail(view: "MarketView", poi_p: POIParams, s: Setup) -> str:
    st = view.states.get(poi_p.range_tf)
    r = swing_range(st) if st is not None else None
    if r is None:
        return " range=None"
    return (f" range_tf={poi_p.range_tf.value} range_low={r[0]}@idx{st.swing_low.index} range_high={r[1]}@idx{st.swing_high.index} "
            f"range_extreme_confirmed={(st.swing_low if st.swing_trend is Trend.BEAR else st.swing_high).confirmed} "
            f"zone_eq={s.poi.eq} poi={s.poi.id} poi_tf={s.poi.tf.value} m15_trend={st.swing_trend.value}")


def side_of(direction: Trend) -> Side:
    return Side.LONG if direction is Trend.BULL else Side.SHORT


def touches(z: Zone, c: Candle) -> bool:
    return c.low <= z.top and c.high >= z.bottom


def outside(z: Zone, c: Candle) -> bool:
    return c.low > z.top if z.kind is ZoneKind.DEMAND else c.high < z.bottom


def visit_start(m1: Sequence[Candle], z: Zone, i: int, max_back: int = 20000) -> int:
    """Mevcut dokunuşun (zonu ardışık kesen/içinde kalan mumlar) ilk M1 mumu."""
    j = i
    while j > 0 and i - j < max_back and not outside(z, m1[j - 1]):
        j -= 1
    return j


def double_bos(m15_events: Sequence[StructureEvent], direction: Trend) -> bool:
    """EN-R007 / D-15 (kullanıcı kararı): M15'te işlem yönünde ARDIŞIK ≥2 BOS (HH + HL; MS-R014 çift BOS), karşı yönlü son BOS'tan beri.
    Warm-up olayları da yapıdır ve sayılır. Q-E1: 'ne zamandan beri' kaynakta yok → karşı yönlü son BOS."""
    n = 0
    for e in reversed(m15_events):
        if e.type is not EventType.BOS:
            continue
        if e.dir is not direction:
            break
        n += 1
    return n >= 2


def choose_entry_zone(choch: StructureEvent, ze: ZoneEngine, requires_sweep: bool) -> tuple[Optional[Zone], str]:
    """EN-R001 adım 5 / EN-R008: CHoCH'a neden olan FLIP zonu varsa (en son doğan; `decisional_flip_requires_sweep` ise sweep almış olmalı)
    onu seçer. Aksi halde (None, 'NONE') döner ve çağıran V tepki kutusunu çizer (`reaction_box`, Q-Z11): M1 giriş kutusu
    SD-R001/R002 zon algılamasına bağlı değildir (DECISIONS §3: M1 giriş kutusu = reaksiyon tabanı→tepesi)."""
    flips = [z for z in ze.zones if z.is_flip and any(e is choch for e in z.caused_events)]
    if flips:
        f = max(flips, key=lambda z: z.created_index)
        if not requires_sweep or ze.sweep_flag(f):
            return f, "FLIP"
    return None, "NONE"


def reaction_box(m1: Sequence[Candle], start: int, end: int, direction: Trend) -> Optional[Zone]:
    """Q-Z11 (kullanıcı tanımı): mitigasyondan (start) M1 CHoCH mumuna (end, dahil) kadarki V tepkisinin giriş kutusu.
    Long: alt = penceredeki en düşük low (ilk yapan mum = taban mumu); üst = taban mumu ile onu doğrudan öncesindeki ardışık
    karşı yönlü (bearish) mumların en yüksek high'ı. Short simetrik (en yüksek high; üst/alt ters; karşı yönlü = bullish)."""
    if end < start or start < 0 or end >= len(m1):
        return None
    long = direction is Trend.BULL
    idx = range(start, end + 1)
    base = min(idx, key=lambda i: (m1[i].low, i)) if long else max(idx, key=lambda i: (m1[i].high, -i))
    first = base
    while first - 1 >= start and ((m1[first - 1].close < m1[first - 1].open) if long else (m1[first - 1].close > m1[first - 1].open)):
        first -= 1
    grp = m1[first:base + 1]
    if long:
        top, bottom = max(c.high for c in grp), m1[base].low
        kind = ZoneKind.DEMAND
    else:
        top, bottom = m1[base].high, min(c.low for c in grp)
        kind = ZoneKind.SUPPLY
    return Zone(f"M1-V{end}-{kind.value[0]}", Timeframe.M1, kind, Origin.V_REACTION, "REACTION", top, bottom, first, end,
                m1[end].open_time)


def fill_touch(side: Side, entry: Decimal, c: Candle, spread: Decimal) -> bool:
    """Limit giriş dokunuşu (bid mumundan): long ask ile (ask = bid + spread), short bid ile dolar."""
    return (c.low + spread <= entry) if side is Side.LONG else (c.high >= entry)


class SignalBook:
    """T-DUP-01 / Q-E5, Q-E6: aynı POI'de ikinci sinyal ve karşıt yönlü sinyal politikası (config'den; varsayılan yok)."""

    def __init__(self, duplicate_policy: str, opposite_policy: str):
        self.dup, self.opp = duplicate_policy, opposite_policy
        self.setups: list[Setup] = []

    def active(self) -> list[Setup]:
        return [s for s in self.setups if s.state in ACTIVE_ORDER_STATES]

    def check(self, new: Setup, time: datetime) -> Optional[tuple[str, str]]:
        """None = izin; aksi halde (neden, kural). REPLACE: bekleyen eski emir iptal edilir (açık pozisyon varsa ret)."""
        for s in self.active():
            if s is new:
                continue
            if s.poi.id == new.poi.id and s.direction is new.direction:
                if self.dup == "ALLOW":
                    continue
                if self.dup == "REPLACE" and s.state is State.ORDER_PENDING:
                    s.to(State.WATCHING, time, "REPLACED_BY_NEW_SIGNAL")
                    continue
                return "DUPLICATE_POI", "FINAL_SPEC §19 / T-DUP-01"
            if s.direction is not new.direction and self.opp != "ALLOW":
                return "OPPOSITE_SIGNAL", "FINAL_SPEC §19"
        return None


# ------------------------------------------------------------------ model
class EntryModel:
    def __init__(self, pair: str, params: EntryParams, poi_params: POIParams, stop_params: StopParams,
                 sizing: SizingParams, clock: SessionClock, tracker: DayLossTracker, mgmt: ManagementParams,
                 news: Optional[NewsCalendar] = None):
        self.pair, self.p, self.poi_p, self.stop_p, self.sizing = pair, params, poi_params, stop_params, sizing
        self.mgmt = mgmt
        self.clock, self.tracker, self.news = clock, tracker, news
        self.setups: list[Setup] = []
        self.archive: list[Setup] = []          # POI geçersizleşip izlemeden çıkan kurulumlar (huni raporu için saklanır)
        self.book = SignalBook(params.duplicate_policy, params.opposite_policy)
        self._engines: dict[str, ZoneEngine] = {}
        self.stats = {"liquidation_window_capped": 0, "liquidation_window_capped_no_sweep": 0}   # Q-L3: sınır nedeniyle etkilenen durumlar

    # ---- kurulum oluşturma (alarm) ----
    def watch(self, zone: Zone, ze: ZoneEngine, zones: Mapping[Timeframe, Sequence[Zone]]) -> Setup:
        """Geçerli, ≥M15 POI için kurulum. Alarm anında sweep (LQ-R002) ve inducement (LQ-R003) bayrakları hesaplanır."""
        from ..liquidity.sweeps import has_inducement
        direction = zone.kind.direction
        s = Setup(f"{self.pair}-{zone.id}-{direction.value}", self.pair, zone, direction)
        ze.sweep_flag(zone)
        s.has_inducement = has_inducement(zone, ze.candles, len(ze.candles), self.p.eq_tol, self.p.pipette)
        self.setups.append(s)
        self.book.setups.append(s)
        self._engines[s.id] = ze
        return s

    # ---- ana adım ----
    def step(self, view: MarketView, live: bool = True) -> list[SignalEvent]:
        out: list[SignalEvent] = []
        c = view.m1[view.i]
        self.new_day(view.now)
        for s in list(self.setups):
            if s.cancelled:
                continue
            if not (s.poi.usable) and s.state in (State.WATCHING, State.POI_MITIGATED, State.CONFIRMATION_PENDING, State.ENTRY_READY):
                s.cancelled = "POI_INVALIDATED"
                if s.state is not State.WATCHING:
                    s.to(State.WATCHING, view.now, "POI_INVALIDATED")
                self.setups.remove(s)
                self.archive.append(s)
                if s in self.book.setups:
                    self.book.setups.remove(s)
                continue
            if not live:
                continue
            if s.state is State.ORDER_PENDING:
                out += self._pending(s, view, c)
            elif s.state is State.WATCHING:
                out += self._watching(s, view, c)
            elif s.state is State.POI_MITIGATED:
                out += self._mitigated(s, view, c)
            elif s.state is State.CONFIRMATION_PENDING:
                out += self._confirming(s, view, c)
        return out

    # ---- WATCHING ----
    def _targets(self, s: Setup, view: MarketView) -> list[Zone]:
        poi = s.poi
        small = (poi.top - poi.bottom) / (self.p.pipette * 10) < self.p.min_refine_pips          # V8: küçük POI rafine edilmez
        if poi.tf.delta >= self.p.refine_min_tf.delta and self.p.require_refined_ltf_zone and not small:        # D-02
            return refined_zones(poi, view.zones.get(Timeframe.M15, ()), self.p.pipette)
        return [poi]

    def _permission(self, s: Setup, view: MarketView, mitigation_time: datetime):
        t4 = view.states[Timeframe.H4].swing_trend
        t15 = view.states[Timeframe.M15].swing_trend
        parents = nested_parents(s.poi, [z for tf in (Timeframe.H4, Timeframe.D1) for z in view.zones.get(tf, ())],
                                 self.p.pipette)
        in_4h = s.poi.tf.delta >= self.p.refine_min_tf.delta or any(p.mitigated_index is not None for p in parents)
        choch = m15_choch_after_mitigation(view.m15_events, mitigation_time, s.direction)       # Q-P1
        perm = check_permission(t4, t15, s.direction, price_in_htf_poi=True, price_in_4h_poi=in_4h,
                                m15_choch_toward_dir=choch)
        cls = None
        if Trend.UNDEFINED not in (t4, t15):
            cls = classify_trend(t4, t15, s.direction)
        return perm, cls

    def _watching(self, s: Setup, view: MarketView, c: Candle) -> list[SignalEvent]:
        if self.p.entry_type != "RISK":
            pz, pp = s.poi, self.p.pipette           # ucuz geometri ön kontrolü (rafine zonlar POI'nin içinde): dokunuş yoksa çık
            if c.low > pz.top + pp or c.high < pz.bottom - pp:
                return []
        if self.tracker.is_locked(view.now) or not self.clock.may_open(view.now).allowed:
            return []                                    # §17: WATCHING aktif koşulları: seans penceresi, günlük kayıp < limit
        if self.p.entry_type == "RISK":
            return self._risk_entry(s, view, c)
        hit = next((z for z in self._targets(s, view) if touches(z, c)), None)
        if hit is None:
            return []
        s.mitigated_zone = hit
        s.visit_start = visit_start(view.m1, hit, view.i)
        s.mitigation_time = view.m1[s.visit_start].open_time
        # liquidation (EN-R001 adım 1) mitigasyon anında, fiyat zonun içindeyken değerlendirilir: süpürme dokunuştan önce/aynı mumda olmalı
        s.liquidation = liquidation(view.m1, hit, view.i, self.p.eq_tol, self.p.pipette, internal_levels(view.m1_struct, max(0, view.i - MAX_WINDOW)))
        if s.liquidation.window_capped:
            self.stats["liquidation_window_capped"] += 1
            if not s.liquidation.found:
                self.stats["liquidation_window_capped_no_sweep"] += 1      # 48 saat sınırı olmasa belki bulunurdu (elenen durum)
        s.to(State.POI_MITIGATED, view.now, f"MITIGATION:{hit.id}")
        _, tc0 = self._permission(s, view, s.mitigation_time)
        s.trend_class = tc0.value if tc0 else "UNKNOWN"
        s.log(view.now, "MITIGATED", f"zone={hit.id} poi_eq={s.poi.eq} liquidation={'FOUND' if s.liquidation.found else s.liquidation.reason}")
        return self._mitigated(s, view, c)

    def _mitigated(self, s: Setup, view: MarketView, c: Candle) -> list[SignalEvent]:
        """POI_MITIGATED: izin (EN-R006/Q-P1) ve karşı-HTF çift BOS (EN-R007). Q-E8 (KULLANICI KARARI): reddedilirse kurulum burada BEKLER —
        POI geçersizleşene kadar her mumda yeniden değerlendirilir (M15 CHoCH sonradan gelebilir); bekleme süresince limit sinyal yok."""
        perm, tclass = self._permission(s, view, s.mitigation_time)
        s.trend_class = tclass.value if tclass else "UNKNOWN"
        if not perm.allowed:
            return self._wait(s, view, "PERMISSION", perm.rule, perm.reason)
        if (tclass is TrendClass.COUNTER_HTF and self.p.counter_htf_require_double_bos
                and not double_bos(view.m15_events, s.direction)):
            return self._wait(s, view, "COUNTER_HTF_NEEDS_DOUBLE_BOS", "EN-R007", "M15'te işlem yönünde ardışık 2 BOS yok")
        s.wait_reason = ""
        s.log(view.now, "PERMISSION_OK", perm.row)
        s.to(State.CONFIRMATION_PENDING, view.now, perm.row)
        return self._confirming(s, view, c)               # dokunuş mumunun kendisinde CHoCH olamaz (indeks > visit_start şartı)

    def _wait(self, s: Setup, view: MarketView, reason: str, rule: str, detail: str) -> list[SignalEvent]:
        if s.wait_reason != reason:                       # aynı nedenle bekleme tek kez kaydedilir
            s.reject(view.now, reason, rule, detail)
            s.log(view.now, f"PERMISSION_WAIT:{reason}", detail)
            s.wait_reason = reason
        return []

    # ---- CONFIRMATION_PENDING ----
    def _confirming(self, s: Setup, view: MarketView, c: Candle) -> list[SignalEvent]:
        if self.tracker.is_locked(view.now):
            s.to(State.WATCHING, view.now, "DAY_LOCKED")
            return []
        for ev in view.m1_events:
            if (ev.type is EventType.CHOCH and ev.dir is s.direction and ev.signal_capable
                    and ev.break_index > s.visit_start):
                s.choch = ev
                return self._enter(s, view, c, ev)
        return []

    def _enter(self, s: Setup, view: MarketView, c: Candle, choch: StructureEvent) -> list[SignalEvent]:
        t = view.now
        ze1 = view.m1_zones
        zone, kind = ((None, "NONE") if self.p.entry_zone_choice == "EXTREME_ALWAYS"
                      else choose_entry_zone(choch, ze1, self.p.decisional_flip_requires_sweep))
        if zone is None:                                     # Q-Z11: flip yoksa V tepki kutusu (zon algılamasından bağımsız)
            zone = reaction_box(view.m1, s.visit_start, choch.break_index, s.direction)
            kind = "EXTREME" if zone is not None else "NONE"
        s.to(State.ENTRY_READY, t, f"CHOCH:{choch.time:%H:%M}")
        s.log(t, "CHOCH", f"choch_time={choch.time.isoformat()} level={choch.level} origin_index={choch.origin_index} "
                          f"break_index={choch.break_index} leg_len={choch.break_index - choch.origin_index}")
        if zone is None:
            s.log(t, "NO_ENTRY_ZONE", _window_zones(ze1, choch))
            return self._abort(s, t, "NO_ENTRY_ZONE", "EN-R001/5", "flip yok ve V tepki kutusu çizilemedi (geçersiz pencere)")
        s.entry_zone, s.entry_zone_kind = zone, kind
        s.log(t, "ENTRY_ZONE_OK", f"{kind} {zone.id} top={zone.top} bottom={zone.bottom}")
        liq = s.liquidation
        vshape = v_shape_exit(s.visit_start, choch.break_index, self.p.v_shape_max_candles)
        return self._finalize(s, view, zone, kind, liq, vshape)

    def _risk_entry(self, s: Setup, view: MarketView, c: Candle) -> list[SignalEvent]:
        side = side_of(s.direction)
        plan0 = plan_entry(ZoneBounds(s.poi.top, s.poi.bottom), side, self.stop_p)
        if isinstance(plan0, EntryPlan) and fill_touch(side, plan0.entry, c, self.p.spread):
            return []                                     # fiyat girişe zaten ulaştı/aştı: bekleyen limit yerleştirilemez
        s.mitigated_zone, s.visit_start, s.mitigation_time = s.poi, view.i, view.m1[view.i].open_time
        for st, why in ((State.POI_MITIGATED, "RISK_ENTRY"), (State.CONFIRMATION_PENDING, "RISK_ENTRY"),
                        (State.ENTRY_READY, "RISK_ENTRY")):
            s.to(st, view.now, why)
        s.entry_zone, s.entry_zone_kind = s.poi, "POI"
        return self._finalize(s, view, s.poi, "POI", None, None)

    def _abort(self, s: Setup, t: datetime, reason: str, rule: str, detail: str = "") -> list[SignalEvent]:
        s.reject(t, reason, rule, detail)
        s.to(State.WATCHING, t, reason)
        log.info("%s reddedildi: %s %s", s.id, reason, detail)
        return [SignalEvent("REJECTED", s, t, reason=reason)]

    def _finalize(self, s: Setup, view: MarketView, zone: Zone, kind: str, liq, vshape) -> list[SignalEvent]:
        t = view.now
        risk_mode = self.p.entry_type == "RISK"
        perm, tclass = self._permission(s, view, s.mitigation_time)
        s.trend_class = tclass.value if tclass else "UNKNOWN"
        poi_params = self.poi_p if not risk_mode else dataclasses.replace(self.poi_p, require_liquidation=False)
        ctx = POIContext(direction=s.direction, states=view.states, permission=perm, session=self.clock.may_open(t),
                         liquidation=liq, has_inducement=s.has_inducement,
                         nested_parents=nested_parents(s.poi, [z for tf in (Timeframe.H4, Timeframe.D1)
                                                               for z in view.zones.get(tf, ())], self.p.pipette),
                         v_shape=vshape, peers=self._engines[s.id].zones)
        res: POIResult = evaluate_poi(s.poi, ctx, poi_params)
        if not res.passed:
            g = res.failed_gates[0]
            for fg in res.failed_gates:
                s.log(t, f"GATE_FAIL:{fg.name}", fg.reason + (_range_detail(view, self.poi_p, s) if fg.name == "range_filter" else ""))
            return self._abort(s, t, f"GATE:{g.name}", g.rule, g.reason)
        side = side_of(s.direction)
        plan = plan_entry(ZoneBounds(zone.top, zone.bottom), side, self.stop_p)
        if isinstance(plan, Rejected):
            return self._abort(s, t, plan.reason, plan.rule, plan.detail)                    # T-EN-06 / SL-R003
        size = position_size(view.balance, plan.entry, plan.stop, self.sizing)
        if isinstance(size, Rejected):
            return self._abort(s, t, size.reason, size.rule, size.detail)
        rej = self.book.check(s, t)
        if rej is not None:
            return self._abort(s, t, rej[0], rej[1])                                          # T-DUP-01
        tplan = build_plan(side, tclass, plan.entry, plan.stop, view.states, view.zones.get(Timeframe.M15, ()), self.mgmt)
        if isinstance(tplan, Rejected):
            return self._abort(s, t, tplan.reason, tplan.rule, tplan.detail)                  # MG-R005: çıkış planı yok
        ft = tplan.first_target
        target = ft.price if ft is not None else None
        note = (self.news.note(t) if self.news is not None else NewsNote(NewsStatus.UNKNOWN)).text(self.clock.display_tz)
        intent = OrderIntent(s.id, self.pair, side, "LIMIT", plan.entry, plan.stop, plan.pip_risk, size.lots, size.units,
                             self.sizing.risk_pct, size.risk_amount, t, s.poi.id, s.poi.tf, zone.id, kind, target, tplan,
                             tuple(split_lots(size.lots, [l.pct for l in tplan.legs], self.sizing.lot_step, self.sizing.min_lot)),
                             tuple((c.name, c.weight, c.earned) for c in res.criteria),
                             view.states[Timeframe.H4].swing_trend.value, view.states[Timeframe.M15].swing_trend.value,
                             self.clock.window_label(t), tclass.value if tclass else "UNKNOWN", res.score, res.max_score,
                             res.breakdown(), res.shares_event_with, note,
                             ("EN-R001", "EN-R006", "SD-R005", "PD-R003", "SL-R001", "SL-R003", "FM-02", "RK-R001",
                              "MG-R001", "MG-R002", "MG-R005"),
                             (s.choch.break_index - s.visit_start) if (s.choch is not None and s.visit_start is not None) else None)
        s.intent = intent
        s.log(t, "SIGNAL", f"{kind} entry={plan.entry} stop={plan.stop}")
        s.to(State.ORDER_PENDING, t, f"SIGNAL:{kind}")
        return [SignalEvent("SIGNAL", s, t, intent)]

    # ---- ORDER_PENDING ----
    def _pending(self, s: Setup, view: MarketView, c: Candle) -> list[SignalEvent]:
        it: OrderIntent = s.intent
        if it.cancel_if_reaches is None:
            return []
        reached = (c.high >= it.cancel_if_reaches) if it.side is Side.LONG else (c.low <= it.cancel_if_reaches)
        if not reached:
            return []
        if fill_touch(it.side, it.entry, c, self.p.spread):
            s.notes.append(f"AMBIGUOUS_FILL_VS_TARGET@{view.now.isoformat()}")      # mum içi sıra bilinmiyor → backtest (tick/stop-first) çözer
            return []
        s.to(State.WATCHING, view.now, "CANCEL_FIRST_TARGET_REACHED_BEFORE_FILL")
        return [SignalEvent("CANCELLED", s, view.now, it, "FIRST_TARGET_REACHED_BEFORE_FILL")]

    # ---- dışarıdan çağrılar (backtest / pozisyon yönetimi) ----
    def mark_filled(self, s: Setup, t: datetime) -> None:
        s.to(State.POSITION_OPEN, t, "FILLED")

    def mark_risk_free(self, s: Setup, t: datetime) -> None:
        """Risk kaldırıldı (4R'de %20 kapandı, MG-R001): POSITION_OPEN → RISK_FREE; scale-in artık mümkün (MG-R004)."""
        s.to(State.RISK_FREE, t, "RISK_REMOVED")

    def mark_closed(self, s: Setup, t: datetime, net_pnl: Decimal) -> State:
        """Pozisyon kapandı: kayıpsa günlük sayaç (RK-R003, Q-P3); 3. kayıpta kurulum DAY_LOCKED, aksi halde WATCHING (§17)."""
        if s.state in (State.POSITION_OPEN, State.RISK_FREE):
            s.to(State.CLOSED, t, f"CLOSED pnl={net_pnl}")
        self.tracker.record_close(t, net_pnl)
        nxt = State.DAY_LOCKED if self.tracker.is_locked(t) else State.WATCHING
        s.to(nxt, t, "AFTER_CLOSE")
        return nxt

    def new_day(self, now: datetime) -> None:
        """Gün sınırı geçildiyse DAY_LOCKED kurulumları IDLE → MAPPING → WATCHING zincirinden serbest bırakır."""
        locked = [s for s in self.setups if s.state is State.DAY_LOCKED]
        if not locked or self.tracker.is_locked(now):
            return
        for s in locked:
            if s.state is State.DAY_LOCKED:
                for st in (State.IDLE, State.MAPPING, State.WATCHING):
                    s.to(st, now, "NEW_DAY")
