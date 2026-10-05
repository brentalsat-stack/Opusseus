"""Pure-Python market indicators for normalized OHLCV candles."""


def _value(candle, short_name, long_name):
    if short_name in candle:
        return float(candle[short_name])
    return float(candle[long_name])


def atr(candles, period=14):
    """Returns the latest simple-average true range over ``period`` candles.

    Returns None when no candles or an invalid period is supplied. The first
    available candle's true range is high-low; subsequent values also include
    the previous close gap.
    """
    period = int(period)
    if period < 1:
        raise ValueError("period pozitif tam sayı olmalı")
    if not candles:
        return None
    ranges = []
    previous_close = None
    for candle in candles:
        high = _value(candle, "h", "high")
        low = _value(candle, "l", "low")
        close = _value(candle, "c", "close")
        if high < low:
            raise ValueError("Mum high değeri low değerinden küçük olamaz")
        true_range = high - low if previous_close is None else max(
            high - low, abs(high - previous_close), abs(low - previous_close)
        )
        ranges.append(true_range)
        previous_close = close
    sample = ranges[-period:]
    return sum(sample) / len(sample)


def swing_points(candles, n):
    """Finds confirmed fractal swings, oldest first, without using future data.

    A point at index ``i`` is returned only when all ``n`` right-side candles
    are present. Each record includes its source index and confirmation index.
    Equal highs/lows do not qualify: the pivot must be strictly more extreme.
    """
    n = int(n)
    if n < 1:
        raise ValueError("n pozitif tam sayı olmalı")
    result = []
    for index in range(n, len(candles) - n):
        high = _value(candles[index], "h", "high")
        low = _value(candles[index], "l", "low")
        left = candles[index - n:index]
        right = candles[index + 1:index + n + 1]
        if all(high > _value(item, "h", "high") for item in left + right):
            result.append({"type": "high", "index": index, "t": candles[index].get("t"),
                           "price": high, "confirmation_index": index + n,
                           "confirmation_t": candles[index + n].get("t")})
        if all(low < _value(item, "l", "low") for item in left + right):
            result.append({"type": "low", "index": index, "t": candles[index].get("t"),
                           "price": low, "confirmation_index": index + n,
                           "confirmation_t": candles[index + n].get("t")})
    result.sort(key=lambda point: (point["index"], point["type"]))
    return result


def find_fvgs(candles):
    """Finds three-candle bullish/bearish gaps and categorizes their fill.

    ``fill_pct`` is one of 0, 50, or 100. Fill is measured by the deepest
    subsequent wick into the gap; candle wicks count. A gap at its formation
    has 0 fill.
    """
    result = []
    for end_index in range(2, len(candles)):
        first = candles[end_index - 2]
        third = candles[end_index]
        first_high = _value(first, "h", "high")
        first_low = _value(first, "l", "low")
        third_high = _value(third, "h", "high")
        third_low = _value(third, "l", "low")
        if first_high < third_low:
            lower, upper = first_high, third_low
            penetration = max((upper - min(upper, _value(c, "l", "low"))) / (upper - lower)
                              for c in candles[end_index + 1:]) if end_index + 1 < len(candles) else 0.0
            result.append({"type": "bullish", "start_index": end_index - 2, "end_index": end_index,
                           "zone_low": lower, "zone_high": upper,
                           "fill_pct": _fill_bucket(penetration)})
        if first_low > third_high:
            lower, upper = third_high, first_low
            penetration = max((max(0.0, min(upper, _value(c, "h", "high")) - lower) / (upper - lower)
                               for c in candles[end_index + 1:]), default=0.0)
            result.append({"type": "bearish", "start_index": end_index - 2, "end_index": end_index,
                           "zone_low": lower, "zone_high": upper,
                           "fill_pct": _fill_bucket(penetration)})
    return result


def _fill_bucket(penetration):
    if penetration <= 0:
        return 0
    if penetration < 1:
        return 50
    return 100


def equal_levels(swings, atr_value, tol):
    """Groups nearby swing highs/lows into EQH/EQL levels.

    Two or more levels qualify when their total price range is no greater
    than ``tol * atr_value``. ``swings`` records may use ``type``/``price``
    (as returned by :func:`swing_points`) or ``kind``/``level``.
    """
    atr_value = float(atr_value)
    tol = float(tol)
    if atr_value < 0 or tol < 0:
        raise ValueError("ATR ve tol negatif olamaz")
    max_distance = atr_value * tol
    normalized = []
    for swing in swings:
        kind = swing.get("type", swing.get("kind", ""))
        price = swing.get("price", swing.get("level"))
        if price is None:
            continue
        kind = str(kind).lower()
        if kind in ("high", "swing_high", "eqh"):
            kind = "high"
        elif kind in ("low", "swing_low", "eql"):
            kind = "low"
        else:
            continue
        normalized.append({"type": kind, "price": float(price), "index": swing.get("index"), "t": swing.get("t")})

    groups = []
    for kind in ("high", "low"):
        levels = sorted((item for item in normalized if item["type"] == kind), key=lambda item: item["price"])
        cluster = []
        for item in levels:
            if cluster and item["price"] - cluster[0]["price"] > max_distance:
                if len(cluster) >= 2:
                    groups.append(_make_equal_group(kind, cluster))
                cluster = []
            cluster.append(item)
        if len(cluster) >= 2:
            groups.append(_make_equal_group(kind, cluster))
    groups.sort(key=lambda group: (group["type"], group["price"]))
    return groups


def _make_equal_group(kind, items):
    prices = [item["price"] for item in items]
    return {"type": "EQH" if kind == "high" else "EQL",
            "price": sum(prices) / len(prices),
            "low": min(prices), "high": max(prices),
            "levels": prices,
            "indices": [item["index"] for item in items],
            "times": [item["t"] for item in items]}
