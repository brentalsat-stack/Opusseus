"""Order block discovery, mitigation state and multi-timeframe stacking."""
import indicators


def _matching_bos_event(ob, structure_events):
    """Return the directional BOS event that produced ``ob``, if available."""
    try:
        bos_index = int(ob["bos_index"])
    except (KeyError, TypeError, ValueError):
        return None
    direction = str(ob.get("direction", "")).upper()
    for event in structure_events or []:
        if (event.get("type") in ("BOS", "BOS_CONFIRMATION")
                and str(event.get("direction", "")).upper() == direction
                and int(event.get("index", -1)) == bos_index):
            return event
    return None


def sweep_then_bos(ob, candles, structure_events=None, lookback=None):
    """True only for the specified opposing swing sweep before the OB's BOS."""
    from config import SWEEP_LOOKBACK, SWING_N

    if structure_events is None:
        import structure
        structure_events = structure.analyze_structure(candles).get("events", [])
    event = _matching_bos_event(ob, structure_events)
    if event is None:
        return False
    direction = str(ob.get("direction", "")).upper()
    wanted_sweep_direction = "BEARISH" if direction == "BULLISH" else "BULLISH"
    wanted_swing_type = "low" if direction == "BULLISH" else "high"
    bos_index = int(event["index"])
    origin = ob.get("origin_index", event.get("origin_index"))
    if origin is None:
        return False
    start = max(0, int(origin) - (SWEEP_LOOKBACK if lookback is None else int(lookback)))
    swings = indicators.swing_points(candles, SWING_N)
    swing_confirmation = {point["index"]: point["confirmation_index"] for point in swings
                          if point["type"] == wanted_swing_type}
    for sweep in structure_events or []:
        sweep_index = int(sweep.get("index", -1))
        if not (start <= sweep_index < bos_index):
            continue
        if (sweep.get("type") == "LIQUIDITY_SWEEP"
                and str(sweep.get("direction", "")).upper() == wanted_sweep_direction
                and int(sweep.get("swing_index", -1)) in swing_confirmation
                and swing_confirmation[int(sweep.get("swing_index", -1))] <= sweep_index):
            return True
    return False


def major_structure_break(ob, candles, structure_events=None, swing_n_major=None):
    """True when this BOS broke a swing confirmed with the major swing width."""
    from config import SWING_N_MAJOR

    if structure_events is None:
        import structure
        structure_events = structure.analyze_structure(candles).get("events", [])
    event = _matching_bos_event(ob, structure_events)
    if event is None:
        return False
    bos_index = int(event["index"])
    direction = str(ob.get("direction", "")).upper()
    swing_type = "high" if direction == "BULLISH" else "low"
    swing_index = event.get("swing_index")
    level = event.get("level")
    try:
        swing_index = int(swing_index)
        level = float(level)
    except (TypeError, ValueError):
        return False
    n = SWING_N_MAJOR if swing_n_major is None else int(swing_n_major)
    for point in indicators.swing_points(candles, n):
        if (point["type"] == swing_type and point["index"] == swing_index
                and point["confirmation_index"] <= bos_index
                and float(point["price"]) == level):
            return True
    return False


def return_profile(ob, candles, v_max_candles=None, v_body_atr=None,
                   corrective_min_candles=None, corrective_body_atr=None):
    """Classify the post-BOS return leg using its first POI revisit."""
    from config import (ATR_PERIOD, V_MAX_CANDLES, V_BODY_ATR,
                        CORRECTIVE_MIN_CANDLES, CORRECTIVE_BODY_ATR)

    result = {"v_reversal_penalty": False, "corrective_return": False,
              "return_leg_candles": 0, "return_average_body": None,
              "return_atr": None}
    if not candles:
        return result
    try:
        bos_index = int(ob["bos_index"])
    except (KeyError, TypeError, ValueError):
        return result
    direction = str(ob.get("direction", "")).upper()
    if direction not in ("BULLISH", "BEARISH") or bos_index + 1 >= len(candles):
        return result

    end_index = len(candles) - 1
    poi_touched = False
    zone_high = float(ob.get("high", ob.get("proximal")))
    zone_low = float(ob.get("low", ob.get("distal")))
    for index in range(bos_index + 1, len(candles)):
        if (_price(candles[index], "l", "low") <= zone_high
                and _price(candles[index], "h", "high") >= zone_low):
            end_index = index
            poi_touched = True
            break
    post_bos = range(bos_index + 1, end_index + 1)
    if direction == "BULLISH":
        extreme_index = max(post_bos, key=lambda i: _price(candles[i], "h", "high"))
    else:
        extreme_index = min(post_bos, key=lambda i: _price(candles[i], "l", "low"))
    # The extreme candle belongs to the outbound impulse, not the return leg.
    leg_indices = range(extreme_index + 1, end_index + 1)
    leg_count = end_index - extreme_index
    if leg_count <= 0:
        result.update({"return_leg_candles": 0,
                       "return_average_body": None,
                       "return_extreme_index": extreme_index,
                       "return_end_index": end_index,
                       "poi_touched": poi_touched})
        return result
    average_body = sum(abs(_price(candles[i], "c", "close") -
                            _price(candles[i], "o", "open")) for i in leg_indices) / leg_count
    atr_end = max(0, extreme_index)
    atr_start = max(0, atr_end - ATR_PERIOD)
    atr_candles = candles[atr_start:atr_end]
    atr_value = indicators.atr(atr_candles, ATR_PERIOD) if atr_candles else None
    result.update({"return_leg_candles": leg_count,
                   "return_average_body": average_body,
                   "return_atr": atr_value,
                   "return_extreme_index": extreme_index,
                   "return_end_index": end_index,
                   "poi_touched": poi_touched})
    if atr_value is None or atr_value <= 0:
        return result
    v_count = V_MAX_CANDLES if v_max_candles is None else int(v_max_candles)
    v_ratio = V_BODY_ATR if v_body_atr is None else float(v_body_atr)
    corrective_count = (CORRECTIVE_MIN_CANDLES if corrective_min_candles is None
                        else int(corrective_min_candles))
    corrective_ratio = (CORRECTIVE_BODY_ATR if corrective_body_atr is None
                        else float(corrective_body_atr))
    result["v_reversal_penalty"] = (poi_touched and leg_count <= v_count
                                    and average_body > v_ratio * atr_value)
    result["corrective_return"] = (leg_count >= corrective_count
                                   and average_body <= corrective_ratio * atr_value)
    return result


def mitigated_left_zone(ob, candles, older_obs):
    """True if this OB's origin-to-BOS leg traded into an older same-side OB."""
    direction = str(ob.get("direction", "")).upper()
    try:
        start = int(ob.get("origin_index"))
        end = int(ob["bos_index"])
    except (TypeError, ValueError, KeyError):
        return False
    if start < 0 or end < start or end >= len(candles):
        return False
    for older in older_obs or []:
        if older is ob or str(older.get("direction", "")).upper() != direction:
            continue
        try:
            if int(older.get("bos_index", end)) >= end:
                continue
            zone_high = float(older.get("high", older.get("proximal")))
            zone_low = float(older.get("low", older.get("distal")))
        except (TypeError, ValueError):
            continue
        for candle in candles[start:end + 1]:
            if (_price(candle, "l", "low") <= zone_high
                    and _price(candle, "h", "high") >= zone_low):
                return True
    return False


def _price(candle, short, long):
    return float(candle[short] if short in candle else candle[long])


def _is_bullish(candle):
    return _price(candle, "c", "close") > _price(candle, "o", "open")


def _is_bearish(candle):
    return _price(candle, "c", "close") < _price(candle, "o", "open")


def _atr_at(candles, index, period):
    start = max(0, index - period + 1)
    return indicators.atr(candles[start:index + 1], min(period, index - start + 1))


def find_order_blocks(candles, structure_result=None, timeframe="4h"):
    """Finds the last opposing candle before each directional BOS impulse.

    ``structure_result`` is the dictionary returned by ``structure.analyze_structure``.
    Only BOS events (including reversal confirmation BOS) generate OBs. When
    event metadata is unavailable, a caller can pass ``{"events": [...]} ``.
    """
    if not structure_result:
        return []
    from config import ATR_PERIOD, DISPLACEMENT_ATR

    events = structure_result.get("events", []) if isinstance(structure_result, dict) else structure_result
    blocks = []
    fvg_list = indicators.find_fvgs(candles)
    for event in events:
        if event.get("type") not in ("BOS", "BOS_CONFIRMATION"):
            continue
        direction = str(event.get("direction", "")).upper()
        if direction not in ("BULLISH", "BEARISH"):
            continue
        bos_index = int(event["index"])
        origin_index = event.get("origin_index")
        search_start = int(origin_index) if origin_index is not None else 0
        if bos_index <= 0 or bos_index >= len(candles):
            continue

        displacement_index = None
        for index in range(search_start + 1, bos_index + 1):
            average_range = _atr_at(candles, index, ATR_PERIOD)
            body = abs(_price(candles[index], "c", "close") - _price(candles[index], "o", "open"))
            aligned = _is_bullish(candles[index]) if direction == "BULLISH" else _is_bearish(candles[index])
            if average_range is not None and average_range > 0 and aligned and body >= DISPLACEMENT_ATR * average_range:
                displacement_index = index
                break
        impulse_start = displacement_index if displacement_index is not None else bos_index

        opposing = _is_bearish if direction == "BULLISH" else _is_bullish
        candidates = [index for index in range(search_start, impulse_start) if opposing(candles[index])]
        if not candidates:
            candidates = [index for index in range(search_start, bos_index) if opposing(candles[index])]
        if not candidates:
            continue
        ob_index = candidates[-1]

        # Refinement: if the candle after the OB does not close through it, the
        # real momentum starts later; the OB moves forward to the candle that
        # immediately precedes the momentum (displacement, else BOS) candle.
        next_index = ob_index + 1
        if next_index < len(candles):
            next_close = _price(candles[next_index], "c", "close")
            ob_high = _price(candles[ob_index], "h", "high")
            ob_low = _price(candles[ob_index], "l", "low")
            failed_to_clear = next_close <= ob_high if direction == "BULLISH" else next_close >= ob_low
            momentum_index = displacement_index if displacement_index is not None else bos_index
            pre_momentum = momentum_index - 1
            if failed_to_clear and ob_index < pre_momentum and pre_momentum >= search_start:
                ob_index = pre_momentum

        candle = candles[ob_index]
        zone_high = _price(candle, "h", "high")
        zone_low = _price(candle, "l", "low")
        proximal = zone_high if direction == "BULLISH" else zone_low
        distal = zone_low if direction == "BULLISH" else zone_high
        eq = (zone_high + zone_low) / 2.0
        leg_start = displacement_index if displacement_index is not None else ob_index + 1
        has_fvg = any(fvg["type"] == ("bullish" if direction == "BULLISH" else "bearish") and
                      leg_start <= fvg["end_index"] <= bos_index for fvg in fvg_list)
        is_extreme = origin_index is not None and ob_index == int(origin_index)
        blocks.append({"direction": direction, "timeframe": timeframe, "index": ob_index,
                       "bos_index": bos_index, "origin_index": origin_index,
                       "bos_level": event.get("level"),
                       "bos_swing_index": event.get("swing_index"),
                       "bos_type": event.get("type"),
                       "high": zone_high, "low": zone_low, "proximal": proximal,
                       "distal": distal, "eq": eq, "has_fvg": has_fvg,
                       "label": "EXTREME" if is_extreme else "DECISIONAL",
                       "displacement_index": displacement_index, "state": "FRESH"})
    return blocks


def evaluate_ob_state(ob, candles, formation_index=None):
    """Returns visit-based FRESH/TAPPED/MITIGATED/INVALID status for an OB."""
    from config import MAX_TOUCHES

    direction = str(ob["direction"]).upper()
    distal = float(ob.get("distal", ob.get("low" if direction == "BULLISH" else "high")))
    eq = float(ob.get("eq", (float(ob["high"]) + float(ob["low"])) / 2.0))
    start = int(ob.get("bos_index", -1) if formation_index is None else formation_index) + 1
    status = "FRESH"
    visits = 0
    inside_visit = False
    reached_eq = False
    for candle in candles[max(0, start):]:
        high = _price(candle, "h", "high")
        low = _price(candle, "l", "low")
        close = _price(candle, "c", "close")
        invalid = close < distal if direction == "BULLISH" else close > distal
        if invalid:
            return {"state": "INVALID", "touches": visits, "reached_eq": reached_eq}
        entered = low <= float(ob["high"]) and high >= float(ob["low"])
        if entered and not inside_visit:
            visits += 1
        inside_visit = entered
        if entered:
            status = "TAPPED"
            reached_eq = reached_eq or (low <= eq if direction == "BULLISH" else high >= eq)
        if reached_eq or visits >= int(MAX_TOUCHES):
            status = "MITIGATED"
    return {"state": status, "touches": visits, "reached_eq": reached_eq}


def stack_obs(ob_d1, ob_h4, ob_h1):
    """Annotates each POI when its zone overlaps same-direction zones on TFs.

    Daily OBs participate in stacking output, but they are not returned as
    standalone POI candidates. Return value contains annotated 4h/1h POIs.
    """
    groups = [("1day", ob_d1 or []), ("4h", ob_h4 or []), ("1h", ob_h1 or [])]
    poi_results = []
    for own_tf, own_obs in groups[1:]:
        for ob in own_obs:
            low = float(ob.get("low", ob.get("distal")))
            high = float(ob.get("high", ob.get("proximal")))
            direction = str(ob["direction"]).upper()
            overlaps = {own_tf}
            for tf, other_obs in groups:
                if tf == own_tf:
                    continue
                for other in other_obs:
                    if str(other["direction"]).upper() != direction:
                        continue
                    other_low = float(other.get("low", other.get("distal")))
                    other_high = float(other.get("high", other.get("proximal")))
                    if low <= other_high and other_low <= high:
                        overlaps.add(tf)
            annotated = dict(ob)
            annotated["stack_tfs"] = [tf for tf in ("1day", "4h", "1h") if tf in overlaps]
            annotated["stack_count"] = len(overlaps)
            poi_results.append(annotated)
    return poi_results
