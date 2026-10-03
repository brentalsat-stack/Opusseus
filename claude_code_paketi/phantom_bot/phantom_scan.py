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


def _symbol_list(args):
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
        top_symbols = data_binance.get_top_symbols(args.top)
        selections.extend((item["symbol"], "crypto") for item in top_symbols)
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


def _levels_from_structure(candles, result):
    swings = indicators.swing_points(candles, config.SWING_N)
    low, high = result.get("range_low"), result.get("range_high")
    if low is None or high is None:
        return {"IRL": [], "ERL": []}
    return liquidity.classify_liquidity_levels(swings, low, high)


def _score_candidate(ob, bias_d1, bias_h4, stack_count, status_data,
                     poi_candles, structure_result, current_price, market, session_info,
                     pd_levels, pw_levels, same_tf_obs=None, active_context=None,
                     location=None, price_levels=None):
    direction = ob["direction"]
    active_context = active_context or _active_context(direction, structure_result)
    location = location or _poi_location(ob, direction, active_context)
    position = location.get("position_pct")
    pd_valid = location.get("pd_valid", False)
    session_tags = session_info["session_tags"]
    all_events = structure_result.get("events", [])
    sweep_then_bos = orderblocks.sweep_then_bos(ob, poi_candles, all_events)
    major_break = orderblocks.major_structure_break(ob, poi_candles, all_events)
    return_flags = orderblocks.return_profile(ob, poi_candles)
    left_zone_mitigated = orderblocks.mitigated_left_zone(ob, poi_candles, same_tf_obs or [])
    htf_aligned = bias_d1 == direction and bias_h4 == direction

    # Both timeframes use independent BOS counters, and the more advanced one
    # is the STATUS source selected by ltf_status.
    levels_found = _levels_from_structure(poi_candles, structure_result)
    is_asia = "ASIA" in session_tags
    level_hints = [{"type": value.get("type", "high" if direction == "BEARISH" else "low"),
                    "price": value.get("price", value.get("level"))}
                   if isinstance(value, dict) else
                   {"type": "high" if direction == "BEARISH" else "low", "price": value}
                   for value in levels_found["IRL"]]
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
        "counter_trend": not htf_aligned,
    }
    score = scoring.score_setup(setup_for_score)
    restriction = ",".join(session_info["entry_restrictions"])
    entry_type = "confirmation" if restriction else "risk"
    if price_levels is None:
        price_levels = signals.levels(
            ob, direction=direction, market=market, symbol=ob.get("symbol"),
            spread_pips=config.FOREX_SPREAD_PIPS.get(ob.get("symbol", ""), config.FOREX_SPREAD_PIPS["DEFAULT"]),
            atr_value=indicators.atr(poi_candles, config.ATR_PERIOD),
            irl_levels=levels_found["IRL"], current_price=current_price,
            entry_type=entry_type, pd_levels=pd_levels, pw_levels=pw_levels,
            targeted_level=active_context.get("targeted"))
    warnings = list(price_levels.get("warnings", []))
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
    stacked_pois = orderblocks.stack_obs(ob_d1, ob_h4, ob_h1)

    reference_time = current_candle.get("t", series["1h"][-1].get("t"))
    pd = liquidity.pdh_pdl(series["1h"], reference_time)
    pw = liquidity.pwh_pwl(series["1h"], reference_time)
    local_time = datetime.fromtimestamp(int(reference_time), timezone.utc)
    tags = sessions.session_tags(local_time)
    entry_restrictions = []
    if sessions.sunday_open_restriction(local_time):
        entry_restrictions.append("SUNDAY")
    if "ASIA" in tags:
        entry_restrictions.append("ASIA")
    if sessions.news_warnings(local_time, symbol, market):
        entry_restrictions.append("NEWS")
    session_info = {"session_tags": tags, "entry_restrictions": entry_restrictions}
    session_info["spread_hour"] = sessions.in_spread_hour(local_time)

    summary = {"symbol": symbol, "htf_bias_d1": bias_d1, "htf_bias_h4": bias_h4,
               "protected": structure_h4.get("protected"), "targeted": structure_h4.get("targeted"),
               "premium_discount": ("Discount" if structure_h4.get("price_position_pct") is not None and
                                    structure_h4["price_position_pct"] < 50 else "Premium" if
                                    structure_h4.get("price_position_pct") is not None else "UNDEFINED")}
    candidates = []
    seen_poi_keys = set()
    for ob in stacked_pois:
        poi_key = (symbol, ob.get("direction"), ob.get("timeframe"),
                   _price_identity(ob.get("proximal")),
                   _price_identity(ob.get("distal")))
        if poi_key in seen_poi_keys:
            continue
        seen_poi_keys.add(poi_key)
        if ob.get("state") in ("MITIGATED", "INVALID"):
            continue
        poi_candles = {"1day": d1, "4h": h4, "1h": h1}.get(ob.get("timeframe"), [])
        ob_state = orderblocks.evaluate_ob_state(
            ob, poi_candles)
        ob["state"] = ob_state["state"]
        if ob["state"] == "INVALID":
            utils.log_file_only("{} {} {} INVALIDATED".format(
                symbol, ob.get("timeframe", "POI"), ob.get("direction", "")))
            continue
        if ob["state"] == "MITIGATED":
            continue
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
        price_levels = signals.levels(
            ob, direction=ob.get("direction"), market=market, symbol=symbol,
            spread_pips=config.FOREX_SPREAD_PIPS.get(symbol, config.FOREX_SPREAD_PIPS["DEFAULT"]),
            atr_value=indicators.atr(poi_candles, config.ATR_PERIOD),
            current_price=current_price, entry_type=session_entry_type,
            pd_levels=pd, pw_levels=pw,
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
            "session_tags": tags,
        }, htf_state=ob_state["state"])
        progress(ob.get("timeframe", "POI"), status_data["status"])
        if status_data["status"] == "INVALIDATED":
            utils.log_file_only("{} {} {} INVALIDATED".format(
                symbol, ob.get("timeframe", "POI"), ob.get("direction", "")))
            continue
        candidate = _score_candidate(ob, bias_d1, bias_h4, ob.get("stack_count", 1),
                                     status_data, poi_candles,
                                     structure_result, current_price, market, session_info, pd, pw,
                                     ob_h4 if ob.get("timeframe") == "4h" else ob_h1,
                                     active_context, location, price_levels)
        candidate.update({"protected": active_context.get("protected"),
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
    print("Uyarı: a-Shell'i tarama boyunca ön planda tutun.")
    selections = _symbol_list(args)
    if not selections:
        raise RuntimeError("Taranacak sembol bulunamadı")
    all_results, summaries, errors = [], [], []
    total = len(selections)

    for index, (symbol, market) in enumerate(selections, 1):
        def progress(tf, state):
            print("[{}/{}] {} {} {}".format(index, total, symbol, tf, state))
        try:
            candidates, summary = _scan_symbol(symbol, market, args.no_cache, progress)
            all_results.extend(candidates)
            summaries.append(summary)
        except Exception as exc:
            message = "{} taraması başarısız: {}".format(symbol, exc)
            errors.append(message)
            utils.log(message)
            traceback_tail = "\n".join(traceback.format_exc().strip().splitlines()[-3:])
            log_path = os.path.join(config.LOGS_DIR, "run_{}.log".format(
                datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            try:
                with open(log_path, "a", encoding="utf-8") as log_file:
                    log_file.write("[{}] {} traceback (son 3 satır):\n{}\n".format(
                        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), symbol,
                        traceback_tail))
            except OSError:
                pass
            print("[{}/{}] {} HATA — devam ediliyor".format(index, total, symbol))

    duration = round(time.monotonic() - started, 2)
    meta = {"scan_time_utc": scan_time, "market": args.market,
            "symbols_scanned": len(summaries), "duration_seconds": duration,
            "error_count": len(errors), "errors": errors, "warnings": [],
            "symbols": summaries, "show_all": args.show_all}
    final_results = report._limit_candidates(all_results, meta)
    paths = report.write_reports(all_results, meta)
    visible = final_results
    counts = {grade: sum(1 for item in visible if item.get("grade") == grade)
              for grade in ("A", "B", "C")}
    print("Tarama tamamlandı: {:.2f} sn — A: {}, B: {}, C: {}".format(
        duration, counts["A"], counts["B"], counts["C"]))
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
        print("Tarama hatası: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
