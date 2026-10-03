"""One-shot Phantom SMC market scanner; data-only, no trading or notifications."""
import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timezone

import config
import data_binance
import data_twelvedata
import indicators
import liquidity
import orderblocks
import report
import scoring
import sessions
import signals
import structure
import utils


TIMEFRAME_MAP = {
    "forex": {"1day": "1day", "4h": "4h", "1h": "1h", "15m": "15min", "5m": "5min"},
    "crypto": {"1day": "1d", "4h": "4h", "1h": "1h", "15m": "15m", "5m": "5m"},
}
ANALYSIS_CANDLES = 160
TIMEFRAME_SECONDS = {"1day": 86400, "4h": 14400, "1h": 3600}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Phantom SMC tarama botu (bilgi amaçlı, tek seferlik)")
    parser.add_argument("--market", choices=("forex", "crypto", "all"), default="all",
                        help="Taranacak piyasa")
    parser.add_argument("--top", type=int, default=config.CRYPTO_TOP_DEFAULT,
                        help="Kriptoda hacme göre seçilecek coin sayısı (varsayılan 35)")
    parser.add_argument("--balance", type=float, default=None, help="İlk sürümde kullanılmıyor")
    parser.add_argument("--risk", type=float, default=None, help="İlk sürümde kullanılmıyor")
    parser.add_argument("--symbols", type=str, default=None, help="Virgülle ayrılmış semboller")
    parser.add_argument("--no-cache", action="store_true", help="Twelve Data önbelleğini kullanma")
    parser.add_argument("--show-all", action="store_true",
                        help="Raporlarda puan eşiğinin altındaki adayları da göster")
    args = parser.parse_args(argv)
    # The operational default remains 35 (with 30–40 recommended); allow
    # smaller explicit lists for the smoke-test command and quick scans.
    if not 1 <= args.top <= config.CRYPTO_TOP_MAX:
        parser.error("--top 1 ile {} arasında olmalı".format(config.CRYPTO_TOP_MAX))
    if args.balance is not None or args.risk is not None:
        print("Not: Bölüm 11 gereği --balance/--risk kabul edilir ancak pozisyon büyüklüğü hesaplanmaz.")
    return args


def _symbol_list(args, errors=None):
    """Build (symbol, market) pairs; a failed crypto universe fetch only skips crypto.

    With ``--market crypto`` there is nothing else to scan, so the failure is raised.
    """
    if args.symbols:
        requested = [part.strip() for part in args.symbols.split(",") if part.strip()]
        if args.market == "forex":
            return [(symbol, "forex") for symbol in requested]
        if args.market == "crypto":
            return [(symbol.upper(), "crypto") for symbol in requested]
        return [(symbol.upper() if "/" not in symbol else symbol, "forex" if "/" in symbol or "XAU" in symbol.upper() else "crypto")
                for symbol in requested]

    selections = []
    if args.market in ("forex", "all"):
        selections.extend((symbol, "forex") for symbol in config.FOREX_SYMBOLS)
    if args.market in ("crypto", "all"):
        try:
            top_symbols = data_binance.get_top_symbols(args.top)
            selections.extend((item["symbol"], "crypto") for item in top_symbols)
        except Exception as exc:
            if args.market == "crypto":
                raise
            message = utils.mask_secrets("Kripto evreni alınamadı, kripto atlandı: {}".format(exc))
            utils.log(message)
            if errors is not None:
                errors.append(message)
    return selections


def _load_symbol_data(symbol, market, no_cache, progress):
    series = {}
    source_map = TIMEFRAME_MAP[market]
    if market == "forex":
        original_ttls = config.TD_CACHE_TTL_SECONDS
        if no_cache:
            config.TD_CACHE_TTL_SECONDS = {}
        try:
            for common_tf, api_interval in source_map.items():
                response = data_twelvedata.get_series_with_last(
                    symbol, api_interval, config.TWELVEDATA_OUTPUTSIZE)
                if response is None:
                    raise RuntimeError("Twelve Data {} verisi yok".format(api_interval))
                candles = response["candles"]
                if not candles:
                    raise RuntimeError("Twelve Data {} aralığında henüz kapanmış mum yok".format(api_interval))
                series[common_tf] = candles
                series[common_tf + "_last"] = response.get("last_candle")
                progress(common_tf, "OK ({})".format(len(candles)))
        finally:
            config.TD_CACHE_TTL_SECONDS = original_ttls
    else:
        for common_tf, api_interval in source_map.items():
            response = data_binance.get_klines(symbol, api_interval, config.BINANCE_KLINE_LIMIT)
            candles = response["candles"]
            # Keep closed bars for all structural/indicator work. last_candle
            # remains available solely as current-price context.
            if not candles:
                raise RuntimeError("Binance {} verisi yok".format(api_interval))
            series[common_tf] = candles
            series[common_tf + "_last"] = response.get("last_candle")
            progress(common_tf, "OK ({})".format(len(candles)))
    return series


def _slice_for_analysis(candles):
    return candles[-ANALYSIS_CANDLES:] if len(candles) > ANALYSIS_CANDLES else candles


def _bias(result):
    trend = result.get("trend", "UNDEFINED")
    return trend if trend in ("BULLISH", "BEARISH") else "UNDEFINED"


def _position_label(result):
    """Premium/Discount label of the latest close inside a structure's active range."""
    position = result.get("price_position_pct")
    if position is None:
        return "UNDEFINED"
    return "Discount" if position < 50 else "Premium"


def _position_valid(direction, result):
    position = result.get("price_position_pct")
    if position is None:
        return False
    return position < 50 if direction == "BULLISH" else position > 50


def _active_context(direction, structure_h4):
    """Resolve the 4h range, protection boundary and target for an OB side."""
    direction = str(direction).upper()
    range_low = structure_h4.get("range_low")
    range_high = structure_h4.get("range_high")
    trend = _bias(structure_h4)
    aligned = trend == direction

    def level_price(value):
        return value.get("price") if isinstance(value, dict) else value

    if aligned:
        protected = level_price(structure_h4.get("protected"))
        targeted = level_price(structure_h4.get("targeted"))
        # Structure may not have a protected/targeted record yet; use the
        # corresponding active range boundary as a safe fallback.
        if protected is None:
            protected = range_low if direction == "BULLISH" else range_high
        if targeted is None:
            targeted = range_high if direction == "BULLISH" else range_low
    else:
        protected = range_low if direction == "BULLISH" else range_high
        targeted = range_high if direction == "BULLISH" else range_low

    return {"range_low": range_low, "range_high": range_high,
            "protected": protected, "targeted": targeted,
            "trend_aligned": aligned}


def _poi_location(ob, direction, context):
    """Return POI premium/discount validity, range validity and range percent."""
    low, high = context.get("range_low"), context.get("range_high")
    if low is None or high is None or float(high) <= float(low):
        return {"pd_valid": False, "range_valid": False, "position_pct": None}
    eq = float(ob.get("eq", (float(ob.get("high", ob.get("proximal"))) +
                              float(ob.get("low", ob.get("distal")))) / 2.0))
    position = (eq - float(low)) / (float(high) - float(low)) * 100.0
    direction = str(direction).upper()
    pd_valid = position < 50.0 if direction == "BULLISH" else position > 50.0
    protected = context.get("protected")
    if protected is None:
        range_valid = False
    elif direction == "BULLISH":
        poi_boundary = float(ob.get("low", ob.get("distal")))
        range_valid = poi_boundary >= float(protected)
    else:
        poi_boundary = float(ob.get("high", ob.get("distal")))
        range_valid = poi_boundary <= float(protected)
    return {"pd_valid": pd_valid, "range_valid": range_valid,
            "position_pct": position}


def _distance_filter(entry, current_price, daily_candles):
    """Check entry-to-market distance against the configured daily ATR cap."""
    daily_atr = indicators.atr(daily_candles, config.ATR_PERIOD)
    if daily_atr is None or daily_atr <= 0:
        return False, daily_atr, None
    distance = abs(float(entry) - float(current_price))
    return distance <= config.MAX_POI_DISTANCE_ATR_D1 * daily_atr, daily_atr, distance


def _session_context(market, symbol, when):
    """Scan-time session tags, entry restrictions and rollover flag.

    Sessions, SUNDAY/ASIA restrictions and rollover are forex-only (Bölüm 6.6);
    crypto only gets NEWS (USD/ALL rows of news.csv).
    """
    tags, restrictions, spread_hour = [], [], False
    if market == "forex":
        tags = sessions.session_tags(when)
        if sessions.sunday_open_restriction(when):
            restrictions.append("SUNDAY")
        if "ASIA" in tags:
            restrictions.append("ASIA")
        spread_hour = sessions.in_spread_hour(when)
    if sessions.news_warnings(when, symbol, market):
        restrictions.append("NEWS")
    return tags, restrictions, spread_hour


def _active_obs(symbol, obs, candles):
    """Evaluate OB states; keep only FRESH/TAPPED blocks (mitigated/invalid are logged)."""
    active = []
    for ob in obs:
        state = orderblocks.evaluate_ob_state(ob, candles)
        ob["state"] = state["state"]
        ob["touches"] = state["touches"]
        if ob["state"] in ("MITIGATED", "INVALID"):
            utils.log_file_only("{} {} {} {}".format(
                symbol, ob.get("timeframe", "POI"), ob.get("direction", ""), ob["state"]))
            continue
        active.append(ob)
    return active


def _refine_poi(ob, htf_candles, m15_candles, m15_obs):
    """Narrow a 4h/1h POI to the 15m OB formed inside its own candle (risk entry zone).

    The 15m OB must be same-direction, still FRESH/TAPPED, lie fully inside the
    HTF zone and start within the HTF OB candle's time span; the latest such
    block wins. Returns zone fields for signals.levels or None (use HTF zone).
    """
    index = ob.get("index")
    seconds = TIMEFRAME_SECONDS.get(ob.get("timeframe"))
    if not isinstance(index, int) or not seconds or not 0 <= index < len(htf_candles):
        return None
    start = int(htf_candles[index]["t"])
    zone_low, zone_high = float(ob["low"]), float(ob["high"])
    tolerance = (zone_high - zone_low) * 1e-9
    fits = [candidate for candidate in m15_obs
            if candidate["direction"] == ob["direction"]
            and start <= int(m15_candles[candidate["index"]]["t"]) < start + seconds
            and candidate["low"] >= zone_low - tolerance and candidate["high"] <= zone_high + tolerance]
    if not fits:
        return None
    best = max(fits, key=lambda candidate: candidate["index"])
    return {key: best[key] for key in ("high", "low", "proximal", "distal", "eq")}


def _liquidity_levels(candles, unswept_only=True):
    """Swing highs/lows plus EQH/EQL groups, each flagged ``swept``.

    By default only the still unswept levels are returned.
    """
    swings = indicators.swing_points(candles, config.SWING_N)
    levels = [{"type": point["type"], "price": point["price"], "index": point["index"]}
              for point in swings]
    atr_value = indicators.atr(candles, config.ATR_PERIOD)
    if atr_value:
        for group in indicators.equal_levels(swings, atr_value, config.EQ_TOL_ATR):
            levels.append({"type": group["type"], "price": group["price"],
                           "index": max(group["indices"])})
    for level in levels:
        later = candles[int(level["index"]) + 1:]
        if level["type"] in ("high", "EQH"):
            level["swept"] = any(float(c["h"]) > level["price"] for c in later)
        else:
            level["swept"] = any(float(c["l"]) < level["price"] for c in later)
    return [level for level in levels if not (unswept_only and level["swept"])]


def _irl_levels(candles, structure_result):
    """Liquidity levels inside the active 4h range (internal range liquidity).

    Swept levels are kept but flagged; signals.levels prefers unswept ones and
    falls back to a swept swing with a TP1_SWEPT_LEVEL warning.
    """
    low, high = structure_result.get("range_low"), structure_result.get("range_high")
    if low is None or high is None:
        return []
    return liquidity.classify_liquidity_levels(
        _liquidity_levels(candles, unswept_only=False), low, high)["IRL"]


def _levels_from_structure(candles, result):
    swings = indicators.swing_points(candles, config.SWING_N)
    low, high = result.get("range_low"), result.get("range_high")
    if low is None or high is None:
        return {"IRL": [], "ERL": []}
    return liquidity.classify_liquidity_levels(swings, low, high)


def _score_candidate(ob, bias_d1, bias_h4, stack_count, status_data,
                     poi_candles, structure_result, current_price, market, session_info,
                     pd_levels, pw_levels, same_tf_obs=None, active_context=None,
                     location=None, price_levels=None, own_structure=None):
    direction = ob["direction"]
    active_context = active_context or _active_context(direction, structure_result)
    location = location or _poi_location(ob, direction, active_context)
    position = location.get("position_pct")
    pd_valid = location.get("pd_valid", False)
    session_tags = session_info["session_tags"]
    # OB indexes belong to the POI timeframe, so events must come from that
    # same timeframe's structure (structure_result is always the 4h context).
    all_events = (own_structure if own_structure is not None else structure_result).get("events", [])
    sweep_then_bos = orderblocks.sweep_then_bos(ob, poi_candles, all_events)
    major_break = orderblocks.major_structure_break(ob, poi_candles, all_events)
    return_flags = orderblocks.return_profile(ob, poi_candles)
    left_zone_mitigated = orderblocks.mitigated_left_zone(ob, poi_candles, same_tf_obs or [])
    htf_aligned = bias_d1 == direction and bias_h4 == direction

    # Both timeframes use independent BOS counters, and the more advanced one
    # is the STATUS source selected by ltf_status.
    levels_found = _levels_from_structure(poi_candles, structure_result)
    is_asia = "ASIA" in session_tags
    level_hints = _liquidity_levels(poi_candles)
    inducement = liquidity.find_inducement(ob, direction, level_hints,
                                            current_price=current_price)
    setup_for_score = {
        "direction": direction,
        "htf_alignment": htf_aligned,
        "stack_count": stack_count,
        "poi_state": ob.get("state"),
        "ob_label": ob.get("label"),
        "sweep": sweep_then_bos,
        "sweep_then_bos": sweep_then_bos,
        "bos_after_sweep": sweep_then_bos,
        "mitigated_left_zone": left_zone_mitigated,
        "fvg": ob.get("has_fvg", False),
        "major_structure_break": major_break,
        "inducement": inducement is not None,
        "premium_discount": pd_valid,
        "corrective_return": return_flags["corrective_return"],
        "v_reversal_penalty": return_flags["v_reversal_penalty"],
        "session_tags": session_tags,
        "asia": is_asia,
        "news": "NEWS" in session_info["entry_restrictions"],
        # Penalty only when the 4h bias is clearly opposite; UNDEFINED is neutral.
        "counter_trend": bias_h4 not in (direction, "UNDEFINED"),
    }
    score = scoring.score_setup(setup_for_score)
    restriction = ",".join(session_info["entry_restrictions"])
    entry_type = "confirmation" if restriction else "risk"
    if price_levels is not None:
        entry_type = price_levels.get("entry_type", entry_type)
    if price_levels is None:
        price_levels = signals.levels(
            ob, direction=direction, market=market, symbol=ob.get("symbol"),
            spread_pips=config.FOREX_SPREAD_PIPS.get(ob.get("symbol", ""), config.FOREX_SPREAD_PIPS["DEFAULT"]),
            atr_value=indicators.atr(poi_candles, config.ATR_PERIOD),
            irl_levels=levels_found["IRL"], current_price=current_price,
            entry_type=entry_type, pd_levels=pd_levels, pw_levels=pw_levels,
            targeted_level=active_context.get("targeted"))
    warnings = list(price_levels.get("warnings", []))
    if status_data["status"] == "WAITING_TAP":
        # Price has not returned to the POI yet, so levels between entry and price
        # are swept by definition; TP1 is only provisional until the tap happens.
        warnings = ["TP1_PROVISIONAL" if item == "TP1_SWEPT_LEVEL" else item for item in warnings]
    if not pd_valid:
        warnings.append("WRONG_PREMIUM_DISCOUNT")
    if session_info.get("spread_hour"):
        warnings.append("SPREAD_HOUR")
    return {
        "market": market, "symbol": ob.get("symbol"), "direction": direction,
        "htf_bias_d1": bias_d1, "htf_bias_h4": bias_h4,
        "poi_tf": ob.get("timeframe"), "poi_stack": ob.get("stack_tfs", []),
        "poi_proximal": ob.get("proximal"), "poi_distal": ob.get("distal"),
        "poi_eq": ob.get("eq"), "poi_state": ob.get("state"),
        "status": status_data["status"], "entry_type": entry_type,
        "entry": price_levels["entry"], "stop": price_levels["stop"],
        "stop_pips_or_pct": price_levels["stop_pips_or_pct"],
        "tp1": price_levels["tp1"], "tp2": price_levels["tp2"],
        "rr_tp1": price_levels["rr_tp1"], "rr_tp2": price_levels["rr_tp2"],
        "score": score["score"], "grade": score["grade"],
        "score_breakdown": score["breakdown"],
        "premium_discount": "Discount" if position is not None and position < 50 else "Premium" if position is not None else "UNDEFINED",
        "sweep": setup_for_score["sweep"], "fvg": ob.get("has_fvg", False),
        "inducement": inducement is not None, "session_tag": ",".join(session_tags),
        "warnings": warnings, "last_price": current_price,
        "ltf_tf": status_data.get("ltf_tf"),
        "entry_restriction": restriction,
    }


def _scan_symbol(symbol, market, no_cache, progress):
    series = _load_symbol_data(symbol, market, no_cache, progress)
    d1 = _slice_for_analysis(series["1day"])
    h4 = _slice_for_analysis(series["4h"])
    h1 = _slice_for_analysis(series["1h"])
    # LTF history is retained in full so older POI touches and confirmations
    # remain visible for HTF zones formed days earlier.
    m15 = series["15m"]
    m5 = series["5m"]
    structure_d1 = structure.analyze_structure(d1)
    structure_h4 = structure.analyze_structure(h4)
    bias_d1, bias_h4 = _bias(structure_d1), _bias(structure_h4)
    current_candle = series.get("1h_last") or series["1h"][-1]
    current_price = float(current_candle.get("c", current_candle.get("close")))

    ob_d1 = orderblocks.find_order_blocks(d1, structure_d1, "1day")
    ob_h4 = orderblocks.find_order_blocks(h4, structure_h4, "4h")
    structure_h1 = structure.analyze_structure(h1)
    ob_h1 = orderblocks.find_order_blocks(h1, structure_h1, "1h")
    for ob in ob_d1 + ob_h4 + ob_h1:
        ob["symbol"] = symbol
        timeframe_candles = {"1day": d1, "4h": h4, "1h": h1}.get(ob.get("timeframe"), [])
        bos_index = ob.get("bos_index")
        if isinstance(bos_index, int) and 0 <= bos_index < len(timeframe_candles):
            # Candle timestamps are interval starts; LTF confirmation begins
            # after the HTF BOS candle has closed.
            ob["bos_time"] = int(timeframe_candles[bos_index]["t"]) + TIMEFRAME_SECONDS[ob["timeframe"]]
        else:
            ob["bos_time"] = None
    # Only live (FRESH/TAPPED) blocks may stack or become POIs; the full lists
    # stay available for the "mitigated left zone" criterion.
    all_obs = {"4h": ob_h4, "1h": ob_h1}
    stacked_pois = orderblocks.stack_obs(
        _active_obs(symbol, ob_d1, d1), _active_obs(symbol, ob_h4, h4),
        _active_obs(symbol, ob_h1, h1))

    reference_time = current_candle.get("t", series["1h"][-1].get("t"))
    pd = liquidity.pdh_pdl(series["1h"], reference_time)
    pw = liquidity.pwh_pwl(series["1h"], reference_time)
    local_time = utils.now_utc()  # restrictions describe the moment of the scan
    tags, entry_restrictions, spread_hour = _session_context(market, symbol, local_time)
    scan_tags = tags
    session_info = {"session_tags": [], "entry_restrictions": entry_restrictions,
                    "spread_hour": spread_hour}

    summary = {"symbol": symbol, "htf_bias_d1": bias_d1, "htf_bias_h4": bias_h4,
               "protected": structure_h4.get("protected"), "targeted": structure_h4.get("targeted"),
               "premium_discount_d1": _position_label(structure_d1),
               "premium_discount": ("Discount" if structure_h4.get("price_position_pct") is not None and
                                    structure_h4["price_position_pct"] < 50 else "Premium" if
                                    structure_h4.get("price_position_pct") is not None else "UNDEFINED")}
    irl_levels = _irl_levels(h4, structure_h4)
    m15_cache = {}

    def refined_15m_obs():
        # 15m structure is only needed when a POI survives the filters.
        if "obs" not in m15_cache:
            structure_m15 = structure.analyze_structure(m15)
            m15_cache["obs"] = _active_obs(
                symbol, orderblocks.find_order_blocks(m15, structure_m15, "15m"), m15)
        return m15_cache["obs"]

    candidates = []
    seen_poi_keys = set()
    for ob in stacked_pois:
        poi_key = (symbol, ob.get("direction"), ob.get("timeframe"),
                   _price_identity(ob.get("proximal")),
                   _price_identity(ob.get("distal")))
        if poi_key in seen_poi_keys:
            continue
        seen_poi_keys.add(poi_key)
        poi_candles = {"1day": d1, "4h": h4, "1h": h1}.get(ob.get("timeframe"), [])
        ob_state = {"state": ob.get("state")}
        # Active range, protected and targeted levels always come from 4h.
        structure_result = structure_h4
        active_context = _active_context(ob.get("direction"), structure_h4)
        location = _poi_location(ob, ob.get("direction"), active_context)
        if not location["pd_valid"]:
            utils.log_file_only("{} {} {} WRONG_PD".format(
                symbol, ob.get("timeframe", "POI"), ob.get("direction", "")))
            continue
        if not location["range_valid"]:
            utils.log_file_only("{} {} {} OUTSIDE_RANGE".format(
                symbol, ob.get("timeframe", "POI"), ob.get("direction", "")))
            continue

        session_entry_type = "confirmation" if entry_restrictions else "risk"
        refined = _refine_poi(ob, poi_candles, m15, refined_15m_obs())
        levels_poi = dict(ob, **refined) if refined else ob
        price_levels = signals.levels(
            levels_poi, direction=ob.get("direction"), market=market, symbol=symbol,
            spread_pips=config.FOREX_SPREAD_PIPS.get(symbol, config.FOREX_SPREAD_PIPS["DEFAULT"]),
            atr_value=indicators.atr(poi_candles, config.ATR_PERIOD),
            current_price=current_price, entry_type=session_entry_type,
            irl_levels=irl_levels, pd_levels=pd, pw_levels=pw,
            targeted_level=active_context.get("targeted"))
        distance_ok, daily_atr, distance = _distance_filter(
            price_levels["entry"], current_price, d1)
        if not distance_ok:
            reason = "DAILY_ATR_UNAVAILABLE" if daily_atr is None or daily_atr <= 0 else "DISTANCE_FILTER"
            utils.log_file_only("{} {} {} {} entry={} last={} daily_atr={} distance={}".format(
                symbol, ob.get("timeframe", "POI"), ob.get("direction", ""), reason,
                price_levels.get("entry"), current_price, daily_atr, distance))
            continue
        status_data = signals.ltf_status(ob, m15, m5, ob.get("stack_count", 1), {
            "sunday": "SUNDAY" in entry_restrictions,
            "asia": "ASIA" in entry_restrictions,
            "news": "NEWS" in entry_restrictions,
            "session_tags": scan_tags,
        }, htf_state=ob_state["state"])
        progress(ob.get("timeframe", "POI"), status_data["status"])
        if status_data["status"] == "INVALIDATED":
            utils.log_file_only("{} {} {} INVALIDATED".format(
                symbol, ob.get("timeframe", "POI"), ob.get("direction", "")))
            continue
        if status_data.get("ltf_ob"):
            # ENTRY1/2_READY: the entry comes from the new LTF OB, not the HTF zone.
            price_levels = signals.levels(
                ob, direction=ob.get("direction"), market=market, symbol=symbol,
                spread_pips=config.FOREX_SPREAD_PIPS.get(symbol, config.FOREX_SPREAD_PIPS["DEFAULT"]),
                atr_value=indicators.atr(poi_candles, config.ATR_PERIOD),
                current_price=current_price,
                entry_type="double_confirmation" if status_data["status"] == "ENTRY2_READY" else "confirmation",
                irl_levels=irl_levels, pd_levels=pd, pw_levels=pw,
                targeted_level=active_context.get("targeted"), ltf_ob=status_data["ltf_ob"])
        # Session label/score belong to the confirmation (LTF BOS) moment, forex only.
        confirmation_time = status_data.get("confirmation_time")
        confirmation_tags = (sessions.session_tags(confirmation_time)
                             if market == "forex" and confirmation_time else [])
        candidate = _score_candidate(ob, bias_d1, bias_h4, ob.get("stack_count", 1),
                                     status_data, poi_candles,
                                     structure_result, current_price, market,
                                     dict(session_info, session_tags=confirmation_tags), pd, pw,
                                     all_obs[ob.get("timeframe")],
                                     active_context, location, price_levels,
                                     own_structure={"1day": structure_d1, "4h": structure_h4,
                                                    "1h": structure_h1}.get(ob.get("timeframe")))
        candidate.update({"refined_15m": bool(refined), "ltf_ob": status_data.get("ltf_ob"),
                          "protected": active_context.get("protected"),
                          "targeted": active_context.get("targeted"),
                          "range_low": active_context.get("range_low"),
                          "range_high": active_context.get("range_high")})
        candidates.append(candidate)

    # Identical same-symbol/direction/TF/zone candidates are emitted once;
    # if duplicate BOS records differ in score, retain the stronger record.
    unique_candidates = {}
    for candidate in candidates:
        key = (candidate.get("symbol"), candidate.get("direction"), candidate.get("poi_tf"),
               _price_identity(candidate.get("poi_proximal")),
               _price_identity(candidate.get("poi_distal")))
        previous = unique_candidates.get(key)
        if previous is None or candidate.get("score", 0) > previous.get("score", 0):
            unique_candidates[key] = candidate
    return list(unique_candidates.values()), summary


def _price_identity(value):
    if value is None:
        return None
    try:
        return round(float(value), 12)
    except (TypeError, ValueError):
        return str(value)


def run_scan(args):
    started = time.monotonic()
    scan_time = datetime.now(timezone.utc)
    utils.ensure_directories()
    data_twelvedata.reset_halt()
    print("Uyarı: a-Shell'i tarama boyunca ön planda tutun.")
    errors = []
    selections = _symbol_list(args, errors)
    if not selections:
        raise RuntimeError("Taranacak sembol bulunamadı")
    all_results, summaries = [], []
    total = len(selections)

    for index, (symbol, market) in enumerate(selections, 1):
        def progress(tf, state):
            print("[{}/{}] {} {} {}".format(index, total, symbol, tf, state))
        if market == "forex" and data_twelvedata.halt_reason():
            message = utils.mask_secrets("{} atlandı: Twelve Data durduruldu ({})".format(
                symbol, data_twelvedata.halt_reason()))
            errors.append(message)
            utils.log_file_only(message)
            print("[{}/{}] {} atlandı (Twelve Data durduruldu)".format(index, total, symbol))
            continue
        try:
            candidates, summary = _scan_symbol(symbol, market, args.no_cache, progress)
            all_results.extend(candidates)
            summaries.append(summary)
        except Exception as exc:
            message = utils.mask_secrets("{} taraması başarısız: {}".format(symbol, exc))
            errors.append(message)
            utils.log(message)
            traceback_tail = "\n".join(traceback.format_exc().strip().splitlines()[-3:])
            utils.log_file_only("{} traceback (son 3 satır):\n{}".format(symbol, traceback_tail))
            print("[{}/{}] {} HATA — devam ediliyor".format(index, total, symbol))

    duration = round(time.monotonic() - started, 2)
    meta = {"scan_time_utc": scan_time, "market": args.market,
            "symbols_scanned": len(summaries), "duration_seconds": duration,
            "error_count": len(errors), "errors": errors, "warnings": [],
            "symbols": summaries, "show_all": args.show_all}
    final_results = report._limit_candidates(all_results, meta)
    paths = report.write_reports(all_results, meta)
    actionable = [item for item in final_results if item.get("actionable", True)]
    far_count = len(final_results) - len(actionable)
    counts = {grade: sum(1 for item in actionable if item.get("grade") == grade)
              for grade in ("A", "B", "C")}
    print("Tarama tamamlandı: {:.2f} sn — A: {}, B: {}, C: {}, Uzak: {}".format(
        duration, counts["A"], counts["B"], counts["C"], far_count))
    print("Rapor dosyaları:")
    for kind, path in paths.items():
        print("  {}: {}".format(kind, path))
    return paths


def main(argv=None):
    args = parse_args(argv)
    try:
        run_scan(args)
    except KeyboardInterrupt:
        print("Kullanıcı tarafından durduruldu.")
        return 130
    except Exception as exc:
        utils.log("Tarama başlatılamadı: {}".format(exc))
        print("Tarama hatası: {}".format(utils.mask_secrets(exc)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
