"""Modül başına zorunlu config alanları (FINAL_SPEC §26, DECISIONS.md).

Bir alan `REQUIRED`, boş veya yoksa ilgili modül başlamaz (fail-fast).
Burada varsayılan DEĞER yoktur; yalnızca "hangi modül hangi alana ihtiyaç duyar"
ve "değer geldiğinde geçerli aralık" bilgisi bulunur.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REQUIRED = "REQUIRED"
PAIR = "{pair}"  # yol içinde `pairs` listesindeki her pariteye genişler

Check = Callable[[Any], "str | None"]  # None = geçerli, str = hata mesajı
When = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class Requirement:
    path: str
    check: Check | None = None
    when: When | None = None  # False ise bu alan bu modül için gerekmez


@dataclass(frozen=True)
class ModuleSpec:
    requires: tuple[Requirement, ...] = ()
    depends_on: tuple[str, ...] = ()


# ---- değer denetleyicileri -------------------------------------------------
def _is_num(v: Any) -> bool:
    return isinstance(v, (int, Decimal)) and not isinstance(v, bool)


def one_of(*allowed: str) -> Check:
    def check(v: Any) -> str | None:
        return None if v in allowed else f"{v!r} geçersiz; izinli: {', '.join(allowed)}"
    return check


def is_bool(v: Any) -> str | None:
    return None if isinstance(v, bool) else f"{v!r} bool olmalı (true/false)"


def num_gt(minimum: int | str) -> Check:
    def check(v: Any) -> str | None:
        if not _is_num(v):
            return f"{v!r} sayı olmalı"
        return None if Decimal(v) > Decimal(minimum) else f"{v} > {minimum} olmalı"
    return check


def num_ge(minimum: int | str) -> Check:
    def check(v: Any) -> str | None:
        if not _is_num(v):
            return f"{v!r} sayı olmalı"
        return None if Decimal(v) >= Decimal(minimum) else f"{v} ≥ {minimum} olmalı"
    return check


def int_ge(minimum: int) -> Check:
    def check(v: Any) -> str | None:
        if not isinstance(v, int) or isinstance(v, bool):
            return f"{v!r} tamsayı olmalı"
        return None if v >= minimum else f"{v} ≥ {minimum} olmalı"
    return check


def pct_of_one(v: Any) -> str | None:  # RK-R001: 0 < risk ≤ %1
    if not _is_num(v):
        return f"{v!r} sayı olmalı"
    return None if Decimal(0) < Decimal(v) <= Decimal("0.01") else f"{v} (0, 0.01] aralığında olmalı (RK-R001 tavanı %1)"


def pct_0_100(v: Any) -> str | None:
    if not _is_num(v):
        return f"{v!r} sayı olmalı"
    return None if Decimal(0) <= Decimal(v) <= Decimal(100) else f"{v} [0, 100] aralığında olmalı"


def iana_tz(v: Any) -> str | None:
    try:
        ZoneInfo(str(v))
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return f"{v!r} geçerli bir IANA saat dilimi değil"
    return None


def utc_only(v: Any) -> str | None:
    return None if v == "UTC" else f"{v!r}: zaman damgaları UTC saklanır, değer 'UTC' olmalı"


def hhmm(v: Any) -> str | None:
    try:
        time.fromisoformat(str(v))
        return None if isinstance(v, str) and len(v) == 5 else f"{v!r} 'HH:MM' olmalı"
    except ValueError:
        return f"{v!r} 'HH:MM' olmalı"


def windows(v: Any) -> str | None:
    if not isinstance(v, list) or not v:
        return "[[başlangıç, bitiş], ...] listesi olmalı"
    for w in v:
        if not (isinstance(w, list) and len(w) == 2):
            return f"{w!r} [başlangıç, bitiş] çifti olmalı"
        for t in w:
            if (err := hhmm(t)) is not None:
                return err
        if time.fromisoformat(w[0]) >= time.fromisoformat(w[1]):
            return f"{w!r}: başlangıç < bitiş olmalı"
    return None


def non_empty_str_list(v: Any) -> str | None:
    ok = isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v)
    return None if ok else "boş olmayan metin listesi olmalı"


def non_empty_str(v: Any) -> str | None:
    return None if isinstance(v, str) and v.strip() else "boş olmayan metin olmalı"


def is_true(v: Any) -> str | None:
    return None if v is True else "true olmalı (canlı veri salt-okuma)"


def is_false(v: Any) -> str | None:
    return None if v is False else "false olmalı (otomatik emir YOK — DECISIONS §1)"


def _partial_mode(cfg: Mapping[str, Any]) -> bool:
    return cfg.get("risk_removal_method") == "PARTIAL"


R = Requirement
POI_CRITERIA = ("bos_and_flip", "swing_break", "nested_zone", "pro_trend", "sweep_zone",
                "inducement", "pivot_zone", "weak_target", "pd_alignment", "corrective_or_vshape")
_TFS = ("D1", "H4", "M15")

MODULES: dict[str, ModuleSpec] = {
    # --- blocker'sız çekirdek ------------------------------------------------
    "data": ModuleSpec((
        R("pairs", non_empty_str_list),
        R("timeframes.htf", one_of("D1", "H4", "M15", "M1")),
        R("timeframes.mtf", one_of("D1", "H4", "M15", "M1")),
        R("timeframes.ltf", one_of("D1", "H4", "M15", "M1")),
        R("timezones.storage", utc_only),
        R("timezones.session", iana_tz),
        R("timezones.display", iana_tz),
        R(f"pair_params.{PAIR}.pip_size", num_gt(0)),
    )),
    "structure": ModuleSpec((  # MS-R001..R009, R014 — D1/H4/M15 (EURUSD)
        *(R(f"swing_min_pullback_pips.{PAIR}.{tf}", num_gt(0)) for tf in _TFS),
        R("swing_threshold_inclusive", is_bool),
        R("min_swing_candles", int_ge(1)),
        R("trend_change_confirmation", one_of("SINGLE_BOS", "DOUBLE_BOS")),
    ), depends_on=("data",)),
    "structure_m1": ModuleSpec((  # M1 swing eşiği: U-13 / MS-R010 kalibrasyonu
        R(f"swing_min_pullback_pips.{PAIR}.M1", num_gt(0)),
    ), depends_on=("structure",)),
    "risk": ModuleSpec((  # RK-R001..R004, SL-R003
        R("risk_pct", pct_of_one),
        R("max_losses_per_day", int_ge(1)),
        R("min_sl_pips", num_ge(2)),
        R("day_reset.tz", iana_tz),
        R("day_reset.time", hhmm),
    ), depends_on=("data",)),
    "risk_sizing": ModuleSpec((  # FM-02 girdileri (broker/hesap bilgisi)
        R(f"pair_params.{PAIR}.pip_value_per_lot", num_gt(0)),
        R(f"pair_params.{PAIR}.lot_step", num_gt(0)),
        R(f"pair_params.{PAIR}.min_lot", num_gt(0)),
        R(f"pair_params.{PAIR}.units_per_lot", num_gt(0)),
        R("account.currency", non_empty_str),
    ), depends_on=("risk",)),
    "session": ModuleSpec((  # SS-R001
        R("sessions_london", windows),
    ), depends_on=("data",)),
    # --- bekleyen kararlara bağlı --------------------------------------------
    "session_blackout": ModuleSpec((  # SS-R002, C-09
        R("blackout.tz", iana_tz),
        R("blackout.start", hhmm),
        R("blackout.end", hhmm),
    ), depends_on=("session",)),
    "zones": ModuleSpec((  # SD-R001..R006 (B-01..B-03)
        R("zone_draw_mode.H4", one_of("RANGE", "PIVOT", "CANDLE", "FRACTAL_WICK")),
        R("zone_draw_mode.M15", one_of("RANGE", "PIVOT", "CANDLE", "FRACTAL_WICK")),
        R("zone_draw_mode.M1", one_of("REACTION_BASE_TO_TOP", "RANGE", "PIVOT", "CANDLE", "FRACTAL_WICK")),
        R("require_refined_ltf_zone_in_htf_poi", is_bool),
        R("range_detection.type", one_of("INSIDE_BAR_CHAIN")),
        R("range_detection.min_candles", int_ge(2)),
        R("range_detection.breakout", one_of("CLOSE_OUTSIDE")),
        R("breakout_strength.extra_criterion", one_of("NONE")),
        R("reaction_min.pips", num_gt(0)),
        R("reaction_min.measured", non_empty_str),
    ), depends_on=("structure",)),
    "liquidity": ModuleSpec((  # LQ-R001..R006 (B-04, B-05)
        R("require_sweep_zone", is_bool),
        R("require_inducement", is_bool),
        R("require_liquidation", is_bool),
        R("eqh_tolerance.pips", num_gt(0)),
        R("v_shape_metric"),
    ), depends_on=("structure",)),
    "strategy": ModuleSpec((  # POI-R004, EN-R001..R009
        R("entry_type", one_of("RISK", "CONFIRMATION", "DOUBLE_CONFIRMATION")),
        R("entry_price_mode", one_of("DISTAL", "EQ", "FIXED_SL")),
        R("fixed_sl_pips", num_ge(2),
          when=lambda c: c.get("entry_price_mode") == "FIXED_SL"),
        R("sl_buffer_pips", num_ge(0)),
        R("decisional_flip_requires_sweep", is_bool),
        R("require_pd_alignment", is_bool),
        R("counter_htf_require_double_bos", is_bool),
        R("pro_trend_reference", one_of("H4", "M15", "BOTH")),
        R("range_extreme_filter.enabled", is_bool),
        R("range_extreme_filter.allowed_band_pct", num_gt(0)),
        R("range_extreme_filter.range_tf", one_of("D1", "H4", "M15")),
        R("swing_hold_confirmation", one_of("H4_TREND_CHANGE", "H4_CHOCH", "M15_CHOCH")),
        *(R(f"poi_scoring.weights.{k}", num_gt(0)) for k in POI_CRITERIA),
    ), depends_on=("structure", "zones", "liquidity", "risk", "risk_sizing",
                   "session", "session_blackout")),
    "management": ModuleSpec((  # MG-R001..R006
        R("risk_removal_method", one_of("PARTIAL", "BE_AT_FIRST_EXEC_BOS")),
        R("partial_pct", pct_0_100, when=_partial_mode),
        R("partial_at_r", num_gt(0), when=_partial_mode),
        R("target_allocation.pro_trend.m15_weak_swing_pct", pct_0_100),
        R("target_allocation.pro_trend.h4_weak_swing_pct", pct_0_100),
        R("target_allocation.counter_trend.allocation_pct", pct_0_100),
        R("target_allocation.range.allocation_pct", pct_0_100),
    ), depends_on=("risk",)),
    "signals": ModuleSpec((  # sinyal çıktısı: haber uyarısı, emir ömrü
        R("news_filter.mode", one_of("WARN_ONLY")),
        R("news_filter.provider", one_of("FOREXFACTORY")),
        R("news_filter.currencies", non_empty_str_list),
        R("news_filter.impact", one_of("HIGH")),
        R("news_filter.scope", one_of("ALL_SIGNALS_OF_DAY")),
        R("order_expiry.mode"),
        R("notifications", non_empty_str_list),
    ), depends_on=("strategy", "management")),
    "execution": ModuleSpec((  # yalnızca adaptör iskeleti; otomatik emir kapalı
        R("mode.auto_order", is_false),
    )),
    "backtest": ModuleSpec((  # §22
        R("intrabar_policy.resolver", one_of("TICK")),
        R("intrabar_policy.fallback", one_of("STOP_FIRST")),
        R("costs.spread", one_of("FROM_DATA")),
        R("costs.commission.model", one_of("PCT_OF_NOTIONAL")),
        R("costs.commission.rate_pct", num_ge(0)),
        R("costs.commission.min_per_order", num_ge(0)),
        R("costs.commission.currency", non_empty_str),
        R("data.backtest.primary"),
    ), depends_on=("signals",)),
    "data_boundaries": ModuleSpec((  # Aşama 1: Q-D01, Q-D02
        R("candle_boundaries.tz", iana_tz),
        R("candle_boundaries.d1_open", hhmm),
        R("candle_boundaries.h4_anchor", hhmm),
        R("candle_price_side", one_of("BID", "ASK")),
    ), depends_on=("data",)),
    "data_cache": ModuleSpec((
        R("data.backtest.cache.db", non_empty_str),
        R("data.backtest.cache.raw_dir", non_empty_str),
    ), depends_on=("data",)),
    "hist_dukascopy": ModuleSpec((
        R("data.backtest.dukascopy.base_url", non_empty_str),
        R("data.backtest.dukascopy.request_delay_s", num_ge(0)),
        R("data.backtest.dukascopy.max_retries", int_ge(0)),
        R(f"pair_params.{PAIR}.symbols.dukascopy", non_empty_str),
    ), depends_on=("data_cache",)),
    "hist_oanda": ModuleSpec((
        R("data.backtest.oanda.rest_host", non_empty_str),
        R("data.backtest.oanda.token_env", non_empty_str),
        R(f"pair_params.{PAIR}.symbols.oanda", non_empty_str),
    ), depends_on=("data_cache",)),
    "live_feed": ModuleSpec((  # IBKR, salt-okuma
        R("data.live.provider", one_of("IBKR")),
        R("data.live.read_only", is_true),
        R("data.live.venue", non_empty_str),
        R("data.live.host", non_empty_str),
        R("data.live.port", int_ge(1)),
        R("data.live.client_id", int_ge(0)),
        R(f"pair_params.{PAIR}.symbols.ibkr", non_empty_str),
    ), depends_on=("data",)),
    "journal": ModuleSpec(),
}

__all__ = ["REQUIRED", "PAIR", "Requirement", "ModuleSpec", "MODULES"]
