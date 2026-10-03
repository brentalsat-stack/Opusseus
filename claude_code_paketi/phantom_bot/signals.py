"""LTF confirmation state and informational entry/stop/target calculations."""
import indicators


def _get(candle, short, long):
    return float(candle[short] if short in candle else candle[long])


def _direction(poi):
    return str(poi.get("direction", poi.get("side", ""))).upper()


def _is_tap(candle, poi):
    return _get(candle, "l", "low") <= float(poi["high"]) and _get(candle, "h", "high") >= float(poi["low"])


def _body_breaks_level(candle, direction, level):
    close = _get(candle, "c", "close")
    return close > level if direction == "BULLISH" else close < level


def _origin_ob_index(candles, direction, segment_start, bos_index, opposing):
    """Opposing candle at the origin (extreme) of the leg that produced the BOS."""
    leg = range(segment_start, bos_index)
    if direction == "BULLISH":
        origin = min(leg, key=lambda i: (_get(candles[i], "l", "low"), i))
    else:
        origin = max(leg, key=lambda i: (_get(candles[i], "h", "high"), -i))
    before = [i for i in opposing if i <= origin]
    return before[-1] if before else opposing[0]


def _zone(candles, index, direction):
    candle = candles[index]
    high, low = _get(candle, "h", "high"), _get(candle, "l", "low")
    return {"index": index, "t": candle.get("t"), "high": high, "low": low,
            "proximal": high if direction == "BULLISH" else low,
            "distal": low if direction == "BULLISH" else high, "eq": (high + low) / 2.0}


def _ltf_bos_events(candles, direction, start_index):
    """Find post-touch same-direction close BOS events with a preceding OB candle."""
    from config import SWING_N, ATR_PERIOD, STRONG_BOS_ATR

    found = []
    broken = set()
    # Compute each confirmed swing once. Filtering by confirmation_index at
    # each candle preserves the same no-look-ahead view as swing_points(prefix).
    all_swings = indicators.swing_points(candles, SWING_N)
    for index in range(max(0, start_index + 1), len(candles)):
        kind = "high" if direction == "BULLISH" else "low"
        eligible = [point for point in all_swings
                    if point["type"] == kind
                    and point["index"] < index
                    and point["confirmation_index"] <= index]
        if not eligible:
            continue
        swing = eligible[-1]
        key = swing["index"]
        if key in broken or not _body_breaks_level(candles[index], direction, swing["price"]):
            continue
        broken.add(key)
        # A confirmation BOS requires a fresh opposing-origin candle since the
        # previous same-direction BOS (the OB at the leg origin).
        segment_start = found[-1]["index"] + 1 if found else start_index + 1
        opposing = [origin for origin in range(segment_start, index)
                    if (_get(candles[origin], "c", "close") < _get(candles[origin], "o", "open")
                        if direction == "BULLISH" else
                        _get(candles[origin], "c", "close") > _get(candles[origin], "o", "open"))]
        if not opposing:
            continue
        ob_index = _origin_ob_index(candles, direction, segment_start, index, opposing)
        atr_sample = candles[max(0, index - ATR_PERIOD + 1):index + 1]
        atr_value = indicators.atr(atr_sample, min(ATR_PERIOD, len(atr_sample)))
        body = abs(_get(candles[index], "c", "close") - _get(candles[index], "o", "open"))
        found.append({"index": index, "t": candles[index].get("t"), "level": swing["price"], "ob": _zone(candles, ob_index, direction),
                      "strong": atr_value is not None and atr_value > 0 and body >= STRONG_BOS_ATR * atr_value})
    return found


def ltf_status(poi, candles_15m, candles_5m, stack_count, session_info=None,
               htf_state=None):
    """Evaluate touch, invalidation and independent 15m/5m confirmation counts.

    Returns a dictionary with ``status``, ``ltf_tf``, ``entry_restriction``,
    per-timeframe BOS counts and event details. Restriction flags do not
    replace the ordinary STATUS value.
    """
    direction = _direction(poi)
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("POI direction BULLISH veya BEARISH olmalı")

    # LTF taps/BOS may only confirm a POI after its originating HTF BOS.
    # A missing timestamp preserves compatibility with standalone callers;
    # the scanner attaches bos_time to every detected OB before calling us.
    bos_time = poi.get("bos_time")
    if bos_time is not None:
        bos_time = int(bos_time)
        candles_15m = [candle for candle in candles_15m
                       if int(candle.get("t", 0)) >= bos_time]
        candles_5m = [candle for candle in candles_5m
                      if int(candle.get("t", 0)) >= bos_time]
    restrictions = []
    info = session_info or {}
    if isinstance(info, (list, tuple, set)):
        active = {str(item).upper() for item in info}
        if "ASIA" in active:
            restrictions.append("ASIA")
    elif isinstance(info, dict):
        for name in ("SUNDAY", "ASIA", "NEWS"):
            if info.get(name.lower()) or info.get(name):
                restrictions.append(name)
        tags = {str(tag).upper() for tag in info.get("session_tags", info.get("sessions", []))}
        if "ASIA" in tags and "ASIA" not in restrictions:
            restrictions.append("ASIA")
    restrictions = list(dict.fromkeys(restrictions))

    distal = float(poi.get("distal", poi["low"] if direction == "BULLISH" else poi["high"]))
    tap_index = None
    invalidated = False
    for index, candle in enumerate(candles_15m):
        close = _get(candle, "c", "close")
        if (close < distal if direction == "BULLISH" else close > distal):
            invalidated = True
        if tap_index is None and _is_tap(candle, poi):
            tap_index = index
    for index, candle in enumerate(candles_5m):
        close = _get(candle, "c", "close")
        if close < distal if direction == "BULLISH" else close > distal:
            invalidated = True
        # LTF tap may first become visible on 5m even if the 15m series is absent.
        if tap_index is None and _is_tap(candle, poi):
            tap_index = index

    ltf_tap_found = tap_index is not None
    counts = {"15m": 0, "5m": 0}
    events = {"15m": [], "5m": []}
    if ltf_tap_found or str(htf_state or "").upper() == "TAPPED":
        # Indices are local to each timeframe; if the tap came from 5m, start
        # the 15m scan at its first candle (the data are assumed same-window).
        tap15 = next((i for i, candle in enumerate(candles_15m) if _is_tap(candle, poi)), None)
        tap5 = next((i for i, candle in enumerate(candles_5m) if _is_tap(candle, poi)), None)
        if tap15 is None and str(htf_state or "").upper() == "TAPPED":
            tap15 = 0 if candles_15m else None
        if tap5 is None and str(htf_state or "").upper() == "TAPPED":
            tap5 = 0 if candles_5m else None
        start15 = tap15 if tap15 is not None else -1
        start5 = tap5 if tap5 is not None else -1
        events["15m"] = _ltf_bos_events(candles_15m, direction, start15)
        events["5m"] = _ltf_bos_events(candles_5m, direction, start5)
        counts = {tf: len(rows) for tf, rows in events.items()}

    if invalidated:
        status, best_tf = "INVALIDATED", None
    else:
        readiness = []
        for tf in ("15m", "5m"):
            count = counts[tf]
            strong = any(item["strong"] for item in events[tf])
            if count >= 2:
                readiness.append((2, tf))
            elif count >= 1 and (int(stack_count) >= 3 or (int(stack_count) == 2 and strong)):
                readiness.append((1, tf))
        if readiness:
            rank, best_tf = max(readiness, key=lambda item: (item[0], item[1] == "5m"))
            status = "ENTRY2_READY" if rank == 2 else "ENTRY1_READY"
        elif ltf_tap_found or str(htf_state or "").upper() == "TAPPED":
            status, best_tf = "TAPPED_NO_BOS", None
        else:
            status, best_tf = "WAITING_TAP", None

    ltf_ob = None
    confirmation_time = None
    if status in ("ENTRY1_READY", "ENTRY2_READY") and best_tf:
        rows = events[best_tf]
        chosen = rows[1] if status == "ENTRY2_READY" else rows[0]
        ltf_ob = dict(chosen["ob"], tf=best_tf)
        confirmation_time = chosen.get("t")
    return {"status": status, "ltf_tf": best_tf, "ltf_ob": ltf_ob,
            "confirmation_time": confirmation_time,
            "entry_restriction": ",".join(restrictions),
            "bos_counts": counts, "bos_events": events}


def levels(poi, direction=None, market="forex", symbol=None, spread_pips=None,
           atr_value=None, irl_levels=None, erl_levels=None, current_price=None,
           entry_type="risk", stop_wick=None, pd_levels=None, pw_levels=None,
           targeted_level=None, ltf_ob=None):
    """Calculate informational entry, stop, nearest targets and R:R.

    TP2 first uses ``targeted_level`` if it is beyond both entry and current
    price, then PDH/PDL and PWH/PWL. TP1 is the nearest IRL between entry and
    TP2 that offers at least 1R. ``risk`` entry uses proximal;
    confirmation entries choose distal when its stop distance is within the
    configured threshold, otherwise EQ.
    """
    from config import (CRYPTO_DISTAL_ENTRY_MAX_ATR, CRYPTO_MIN_STOP_PCT,
                        CRYPTO_STOP_BUFFER_ATR, DISTAL_ENTRY_MAX_PIPS,
                        FOREX_MIN_STOP_PIPS, FOREX_SPREAD_PIPS,
                        FOREX_STOP_BUFFER_MIN_PIPS, PIP_SIZE_DEFAULT,
                        PIP_SIZE_JPY, PIP_SIZE_XAU)

    direction = str(direction or _direction(poi)).upper()
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("direction BULLISH veya BEARISH olmalı")
    if ltf_ob:
        # Confirmation entries are placed on the new LTF OB, not on the HTF zone.
        poi = dict(poi, **{key: ltf_ob[key] for key in ("high", "low", "proximal", "distal", "eq")})
    market = str(market).lower()
    is_crypto = market == "crypto"
    symbol_text = str(symbol or poi.get("symbol", "")).upper()
    low = float(poi.get("low", poi.get("distal")))
    high = float(poi.get("high", poi.get("proximal")))
    distal = float(poi.get("distal", low if direction == "BULLISH" else high))
    proximal = float(poi.get("proximal", high if direction == "BULLISH" else low))
    eq = float(poi.get("eq", (low + high) / 2.0))
    if symbol_text.startswith("XAU") or "XAU/" in symbol_text:
        pip_size = PIP_SIZE_XAU
    elif "JPY" in symbol_text:
        pip_size = PIP_SIZE_JPY
    else:
        pip_size = PIP_SIZE_DEFAULT

    if is_crypto:
        atr_value = float(atr_value or 0.0)
        buffer = CRYPTO_STOP_BUFFER_ATR * atr_value
        stop = min(distal, float(stop_wick)) - buffer if direction == "BULLISH" and stop_wick is not None else (
            max(distal, float(stop_wick)) + buffer if direction == "BEARISH" and stop_wick is not None else
            distal - buffer if direction == "BULLISH" else distal + buffer)
        min_distance = (float(poi.get("reference_price", current_price or eq)) * CRYPTO_MIN_STOP_PCT / 100.0)
        if abs(distal - stop) < min_distance:
            stop = distal - min_distance if direction == "BULLISH" else distal + min_distance
        entry = proximal
        if str(entry_type).lower() in ("confirmation", "double_confirmation", "confirmation_entry", "entry1", "entry2"):
            limit = CRYPTO_DISTAL_ENTRY_MAX_ATR * atr_value
            entry = distal if abs(distal - stop) <= limit else eq
        stop_distance = abs(entry - stop)
        stop_metric = (stop_distance / entry * 100.0) if entry else None
        stop_unit = "pct"
    else:
        spread = float(spread_pips if spread_pips is not None else
                       FOREX_SPREAD_PIPS.get(str(symbol or poi.get("symbol", "")), FOREX_SPREAD_PIPS["DEFAULT"]))
        buffer_pips = max(spread, FOREX_STOP_BUFFER_MIN_PIPS)
        buffer = buffer_pips * pip_size
        stop = min(distal, float(stop_wick)) - buffer if direction == "BULLISH" and stop_wick is not None else (
            max(distal, float(stop_wick)) + buffer if direction == "BEARISH" and stop_wick is not None else
            distal - buffer if direction == "BULLISH" else distal + buffer)
        min_distance = FOREX_MIN_STOP_PIPS * pip_size
        if abs(distal - stop) < min_distance:
            stop = distal - min_distance if direction == "BULLISH" else distal + min_distance
        entry = proximal
        if str(entry_type).lower() in ("confirmation", "double_confirmation", "confirmation_entry", "entry1", "entry2"):
            distal_stop_pips = abs(distal - stop) / pip_size
            entry = distal if distal_stop_pips <= DISTAL_ENTRY_MAX_PIPS else eq
        stop_distance = abs(entry - stop)
        stop_metric = stop_distance / pip_size if pip_size else None
        stop_unit = "pips"

    def normalize_levels(values):
        normalized = []
        for value in values or []:
            raw = value.get("price", value.get("level")) if isinstance(value, dict) else value
            if raw is not None:
                normalized.append(float(raw))
        return normalized

    current = float(current_price) if current_price is not None else entry
    def beyond_market(price):
        return price > max(entry, current) if direction == "BULLISH" else price < min(entry, current)

    def first_valid(values):
        for value in normalize_levels(values):
            if beyond_market(value):
                return value
        return None

    tp2 = first_valid([targeted_level])
    fallback_key = "PDH" if direction == "BULLISH" else "PDL"
    week_key = "PWH" if direction == "BULLISH" else "PWL"
    pd_levels, pw_levels = pd_levels or {}, pw_levels or {}
    if tp2 is None:
        tp2 = first_valid([pd_levels.get(fallback_key)])
    if tp2 is None:
        tp2 = first_valid([pw_levels.get(week_key)])

    risk_distance = stop_distance
    warnings = []
    tp1 = None
    if tp2 is not None and risk_distance > 0:
        # Unswept IRL first; a swept swing is only a fallback (TP1_SWEPT_LEVEL).
        tiers = {False: [], True: []}
        for value in irl_levels or []:
            raw = value.get("price", value.get("level")) if isinstance(value, dict) else value
            if raw is None:
                continue
            price = float(raw)
            swept = bool(value.get("swept")) if isinstance(value, dict) else False
            between = entry < price < tp2 if direction == "BULLISH" else tp2 < price < entry
            if between and abs(price - entry) / risk_distance >= 1.0:
                tiers[swept].append(price)
        for swept in (False, True):
            if tiers[swept]:
                tp1 = min(tiers[swept]) if direction == "BULLISH" else max(tiers[swept])
                if swept:
                    warnings.append("TP1_SWEPT_LEVEL")
                break

    def rr(target):
        if target is None or stop_distance == 0:
            return None
        return abs(target - entry) / stop_distance

    return {"direction": direction, "market": market, "entry_type": entry_type,
            "entry": entry, "stop": stop, "stop_distance": stop_distance,
            "stop_pips_or_pct": stop_metric, "stop_unit": stop_unit,
            "tp1": tp1, "tp2": tp2, "rr_tp1": rr(tp1), "rr_tp2": rr(tp2),
            "warnings": (["NO_TARGET"] if tp2 is None else []) + warnings}
