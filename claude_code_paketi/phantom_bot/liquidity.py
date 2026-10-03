"""Liquidity event, inducement and reference-level helpers."""
from datetime import datetime, timezone


def _get(candle, short, long):
    return float(candle[short] if short in candle else candle[long])


def detect_sweeps(candles, levels):
    """Return wick-through/close-back events for supplied levels.

    Levels may be numeric or dictionaries with ``price`` and optional
    ``type``/``direction``. Sweep-up is a high above a level that closes at
    or below it; sweep-down is the symmetric case.
    """
    results = []
    for index, candle in enumerate(candles):
        high, low, close = (_get(candle, "h", "high"), _get(candle, "l", "low"),
                            _get(candle, "c", "close"))
        for raw in levels:
            level = raw if isinstance(raw, (int, float)) else raw.get("price", raw.get("level"))
            if level is None:
                continue
            level = float(level)
            direction = str(raw.get("direction", "") if isinstance(raw, dict) else "").upper()
            kind = str(raw.get("type", "") if isinstance(raw, dict) else "").upper()
            if direction == "BEARISH" or kind in ("HIGH", "EQH", "SWING_HIGH"):
                swept = high > level and close <= level
                sweep_direction = "BEARISH"
            elif direction == "BULLISH" or kind in ("LOW", "EQL", "SWING_LOW"):
                swept = low < level and close >= level
                sweep_direction = "BULLISH"
            else:
                up = high > level and close <= level
                down = low < level and close >= level
                swept = up or down
                sweep_direction = "BEARISH" if up else "BULLISH"
            if swept:
                results.append({"type": "LIQUIDITY_SWEEP", "direction": sweep_direction,
                                "index": index, "t": candle.get("t"), "level": level})
    return results


def find_inducement(poi, direction, levels, current_price=None):
    """Find nearest unswept swing/EQ liquidity between price and an OB POI.

    For bullish setups, EQL/swing lows are inducement below a bullish POI;
    for bearish setups, EQH/swing highs are above a bearish POI.
    """
    direction = str(direction).upper()
    poi_low = float(poi.get("low", poi.get("distal", poi.get("price", 0))))
    poi_high = float(poi.get("high", poi.get("proximal", poi.get("price", 0))))
    candidates = []
    for raw in levels:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type", raw.get("kind", ""))).upper()
        price = raw.get("price", raw.get("level"))
        if price is None:
            continue
        price = float(price)
        if direction == "BULLISH" and kind in ("LOW", "SWING_LOW", "EQL") and price < poi_low:
            if current_price is None or price > float(current_price):
                candidates.append(raw)
        elif direction == "BEARISH" and kind in ("HIGH", "SWING_HIGH", "EQH") and price > poi_high:
            if current_price is None or price < float(current_price):
                candidates.append(raw)
    if not candidates:
        return None
    # Closest candidate to the POI on its inducement side.
    return min(candidates, key=lambda item: abs(float(item.get("price", item.get("level"))) -
                                                  (poi_low if direction == "BULLISH" else poi_high)))


def classify_liquidity_levels(swings, range_low, range_high):
    """Split supplied swing/EQ levels into active-range IRL and outside ERL."""
    low, high = float(range_low), float(range_high)
    irl, erl = [], []
    for level in swings:
        price = float(level.get("price", level.get("level")))
        (irl if low <= price <= high else erl).append(level)
    return {"IRL": irl, "ERL": erl}


def previous_period_levels(candles, period="day", reference_time=None):
    """Calculate previous UTC day/week high and low from normalized candles.

    ``reference_time`` may be an aware/naive datetime or epoch seconds. The
    period preceding the reference timestamp is used. If omitted, latest
    candle time is used.
    """
    if not candles:
        return {"high": None, "low": None}
    if reference_time is None:
        reference_time = candles[-1].get("t")
    if isinstance(reference_time, (int, float)):
        reference_time = datetime.fromtimestamp(reference_time, timezone.utc)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    reference_time = reference_time.astimezone(timezone.utc)
    if period.lower() in ("day", "1d", "daily"):
        current_start = reference_time.replace(hour=0, minute=0, second=0, microsecond=0)
        previous_start = current_start.timestamp() - 86400
        current_start = current_start.timestamp()
    elif period.lower() in ("week", "1w", "weekly"):
        monday = reference_time.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = monday - __import__("datetime").timedelta(days=monday.weekday())
        current_start = monday.timestamp()
        previous_start = current_start - 7 * 86400
    else:
        raise ValueError("period 'day' veya 'week' olmalı")
    values = [c for c in candles if previous_start <= int(c["t"]) < current_start]
    if not values:
        return {"high": None, "low": None}
    return {"high": max(_get(c, "h", "high") for c in values),
            "low": min(_get(c, "l", "low") for c in values)}


def pdh_pdl(candles, reference_time=None):
    """Previous UTC day high/low."""
    levels = previous_period_levels(candles, "day", reference_time)
    return {"PDH": levels["high"], "PDL": levels["low"]}


def pwh_pwl(candles, reference_time=None):
    """Previous UTC week high/low."""
    levels = previous_period_levels(candles, "week", reference_time)
    return {"PWH": levels["high"], "PWL": levels["low"]}
