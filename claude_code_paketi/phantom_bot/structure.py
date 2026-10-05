"""Tip 2 market structure, BOS/CHoCH state machine and range location."""
import indicators


def _get(candle, short, long):
    return float(candle[short] if short in candle else candle[long])


def analyze_structure(candles):
    """Analyze normalized candles and return trend, levels and chronological events.

    Swing points use wick highs/lows and become visible only after their right
    ``SWING_N`` candles are present. BOS and CHoCH require a close beyond the
    relevant swing level; wick-only breaks are emitted as LIQUIDITY_SWEEP.
    """
    from config import SWING_N

    if len(candles) < 1:
        return {"trend": "UNDEFINED", "last_bos": None, "protected": None,
                "targeted": None, "range_high": None, "range_low": None,
                "eq": None, "price_position_pct": None, "events": []}

    trend = "UNDEFINED"
    events = []
    last_bos = None
    last_swing_high = None
    last_swing_low = None
    protected = None
    targeted = None
    active_high = None
    active_low = None
    active_dir = None  # direction of the move the active range belongs to
    broken_levels = set()
    choch_direction = None
    bos_after_choch = 0
    known_swing_indices = set()

    # Prefix evaluation keeps every event causal: index i only sees pivots
    # whose required right-side candles have closed by i.
    for index, candle in enumerate(candles):
        close = _get(candle, "c", "close")
        high = _get(candle, "h", "high")
        low = _get(candle, "l", "low")
        confirmed = indicators.swing_points(candles[:index + 1], SWING_N)
        for swing in confirmed:
            key = (swing["type"], swing["index"])
            if key in known_swing_indices:
                continue
            known_swing_indices.add(key)
            if swing["type"] == "high":
                last_swing_high = swing
            else:
                last_swing_low = swing

        # Detect closed-body breaks and wick-only sweeps against the latest
        # confirmed levels. A level can only produce one event.
        candidates = []
        for kind, swing, crossed in (
            ("BULLISH", last_swing_high, high), ("BEARISH", last_swing_low, low)
        ):
            if swing is None:
                continue
            level_key = (kind, swing["index"])
            if level_key in broken_levels:
                continue
            level = swing["price"]
            body_break = close > level if kind == "BULLISH" else close < level
            wick_cross = crossed > level if kind == "BULLISH" else crossed < level
            if body_break:
                candidates.append((kind, swing, level_key, level))
            elif wick_cross:
                events.append({"type": "LIQUIDITY_SWEEP", "direction": kind,
                               "index": index, "t": candle.get("t"), "level": level,
                               "swing_index": swing["index"]})

        for direction, swing, level_key, level in candidates:
            broken_levels.add(level_key)
            if direction == "BULLISH":
                origin = last_swing_low
                event_type = "BOS"
                if trend == "BEARISH" or trend == "CHOCH_BULLISH":
                    if trend == "BEARISH":
                        trend = "CHOCH_BULLISH"
                        choch_direction = "BULLISH"
                        bos_after_choch = 0
                        event_type = "CHoCH"
                    elif choch_direction == "BULLISH":
                        bos_after_choch += 1
                        if bos_after_choch >= 1:
                            trend = "BULLISH"
                            choch_direction = None
                            event_type = "BOS_CONFIRMATION"
                    else:
                        event_type = "BOS"
                else:
                    trend = "BULLISH"
                    choch_direction = None
                # A CHoCH is only the first break against the trend: the old trend's
                # protected level, target and range stay in force until it is confirmed.
                if event_type != "CHoCH":
                    if origin is not None:
                        protected = {"type": "low", "price": origin["price"], "index": origin["index"]}
                    targeted = {"type": "high", "price": level, "index": swing["index"]}
                    active_low = protected["price"] if protected else (origin["price"] if origin else None)
                    active_high = level
                    active_dir = "BULLISH"
            else:
                origin = last_swing_high
                event_type = "BOS"
                if trend == "BULLISH" or trend == "CHOCH_BEARISH":
                    if trend == "BULLISH":
                        trend = "CHOCH_BEARISH"
                        choch_direction = "BEARISH"
                        bos_after_choch = 0
                        event_type = "CHoCH"
                    elif choch_direction == "BEARISH":
                        bos_after_choch += 1
                        if bos_after_choch >= 1:
                            trend = "BEARISH"
                            choch_direction = None
                            event_type = "BOS_CONFIRMATION"
                    else:
                        event_type = "BOS"
                else:
                    trend = "BEARISH"
                    choch_direction = None
                if event_type != "CHoCH":
                    if origin is not None:
                        protected = {"type": "high", "price": origin["price"], "index": origin["index"]}
                    targeted = {"type": "low", "price": level, "index": swing["index"]}
                    active_high = protected["price"] if protected else (origin["price"] if origin else None)
                    active_low = level
                    active_dir = "BEARISH"

            last_bos = {"direction": direction, "level": level, "index": index,
                        "swing_index": swing["index"], "type": event_type}
            events.append({"type": event_type, "direction": direction, "index": index,
                           "t": candle.get("t"), "level": level,
                           "swing_index": swing["index"],
                           "origin_index": origin["index"] if origin else None})

    # Active range: protected level -> latest swing extreme in the move's direction
    # (uptrend: protected low -> highest confirmed swing high since it). The target
    # is that range edge, so range, protected and targeted always agree.
    if active_dir and protected is not None:
        swings = indicators.swing_points(candles, SWING_N)
        if active_dir == "BULLISH":
            highs = [point for point in swings if point["type"] == "high"
                     and point["index"] >= protected["index"]]
            top = max(highs, key=lambda point: point["price"]) if highs else None
            if top is not None and active_high is not None and top["price"] >= active_high:
                active_high = top["price"]
                targeted = {"type": "high", "price": top["price"], "index": top["index"]}
        else:
            lows = [point for point in swings if point["type"] == "low"
                    and point["index"] >= protected["index"]]
            bottom = min(lows, key=lambda point: point["price"]) if lows else None
            if bottom is not None and active_low is not None and bottom["price"] <= active_low:
                active_low = bottom["price"]
                targeted = {"type": "low", "price": bottom["price"], "index": bottom["index"]}
    range_values = [value for value in (active_high, active_low) if value is not None]
    range_high = max(range_values) if len(range_values) == 2 else None
    range_low = min(range_values) if len(range_values) == 2 else None
    eq = (range_high + range_low) / 2 if range_high is not None else None
    price = _get(candles[-1], "c", "close")
    position_pct = None
    if range_high is not None and range_high > range_low:
        position_pct = (price - range_low) / (range_high - range_low) * 100

    return {"trend": trend, "last_bos": last_bos, "protected": protected,
            "targeted": targeted, "range_high": range_high, "range_low": range_low,
            "eq": eq, "price_position_pct": position_pct, "events": events}
