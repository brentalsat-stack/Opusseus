"""Adım 5 sentetik piyasa yapısı testleri."""
import indicators
import structure


def candle(open_, high, low, close, t):
    return {"t": t, "o": float(open_), "h": float(high), "l": float(low), "c": float(close), "v": 1.0}


def show(name, passed):
    print("{}: {}".format(name, "GEÇTİ" if passed else "KALDI"))
    return passed


def sweep_series():
    # Mum index 2'de swing high=10; iki sağ mumdan sonra index 5 fitille aşar.
    return [candle(7, 8, 6, 7, 0), candle(8, 9, 7, 8, 1),
            candle(9, 10, 8, 9, 2), candle(8, 9, 7, 8, 3),
            candle(8, 9, 7, 8, 4), candle(9, 11, 8, 9.5, 5)]


def body_break_series():
    return [candle(7, 8, 6, 7, 0), candle(8, 9, 7, 8, 1),
            candle(9, 10, 8, 9, 2), candle(8, 9, 7, 8, 3),
            candle(8, 9, 7, 8, 4), candle(10, 11, 8, 10.5, 5)]


def reversal_series():
    # Create an initial bullish BOS, protected low break (CHoCH), then two
    # bearish BOS closes after separate confirmed swing lows.
    return [
        candle(5, 6, 4, 5, 0), candle(6, 7, 5, 6, 1), candle(7, 8, 6, 7, 2),
        candle(7, 9, 6, 8, 3), candle(8, 8.5, 6.5, 7, 4), candle(7, 7.5, 5.5, 6, 5),
        candle(7, 9, 6, 8.5, 6), candle(8, 8.5, 7, 8, 7), candle(8, 8.2, 6.8, 7.2, 8),
        candle(7, 7.5, 5, 5.5, 9), candle(6, 6.5, 4.8, 5.8, 10), candle(6, 7, 5.5, 6.5, 11),
        candle(6, 6.2, 4, 4.5, 12), candle(5, 5.8, 4.2, 5, 13), candle(5, 5.5, 3.5, 4, 14),
        candle(4, 4.5, 3.8, 4.2, 15),
    ]


def test_sweep_not_bos():
    result = structure.analyze_structure(sweep_series())
    sweep = any(event["type"] == "LIQUIDITY_SWEEP" and event["direction"] == "BULLISH" for event in result["events"])
    bos = any(event["type"] == "BOS" and event["direction"] == "BULLISH" for event in result["events"])
    return sweep and not bos


def test_close_is_bos():
    result = structure.analyze_structure(body_break_series())
    return any(event["type"] == "BOS" and event["direction"] == "BULLISH" for event in result["events"])


def test_choch_then_second_bos():
    candles = [candle(7, 8, 6, 7, 0), candle(7, 8, 5, 7, 1),
               candle(9, 10, 4, 9, 2), candle(8, 9, 4.5, 8, 3),
               candle(11, 12, 6, 11, 4), candle(4, 5, 3.5, 4, 5),
               candle(5, 6, 4.5, 5, 6), candle(3.5, 4, 3, 3.5, 7),
               candle(4, 5, 3.5, 4, 8), candle(2.5, 3, 2, 2.5, 9)]
    original = indicators.swing_points

    def fixture_swings(prefix, n):
        points = []
        if len(prefix) >= 3:
            points.extend([{"type": "low", "index": 1, "price": 5, "t": 1},
                           {"type": "high", "index": 2, "price": 10, "t": 2}])
        if len(prefix) >= 8:
            points.append({"type": "low", "index": 5, "price": 4, "t": 5})
        if len(prefix) >= 10:
            points.append({"type": "low", "index": 7, "price": 3, "t": 7})
        return points

    indicators.swing_points = fixture_swings
    try:
        full = structure.analyze_structure(candles)
        choch = next((event for event in full["events"] if event["type"] == "CHoCH" and
                      event["direction"] == "BEARISH"), None)
        if choch is None:
            return False
        before_confirmation = structure.analyze_structure(candles[:7])
        after_confirmation = structure.analyze_structure(candles[:8])
        later_bearish = [event for event in full["events"] if event["direction"] == "BEARISH" and
                         event["type"] in ("BOS", "BOS_CONFIRMATION") and event["index"] > choch["index"]]
        # CHoCH ilk kırılımdır; ardından tek bir BOS trendi çevirir (Adım 31'de ayrıca test edilir).
        return (before_confirmation["trend"] == "CHOCH_BEARISH" and len(later_bearish) >= 1 and
                after_confirmation["trend"] == "BEARISH" and full["trend"] == "BEARISH")
    finally:
        indicators.swing_points = original


def test_premium_discount_position():
    candles = [candle(7, 8, 0, 7, 0), candle(8, 9, 1, 8, 1),
               candle(9, 10, 2, 9, 2), candle(8, 9, 1, 8, 3),
               candle(8, 9, 1, 8, 4), candle(10, 11, 1, 10.5, 5),
               candle(2, 3, 0, 2.5, 6)]
    original = indicators.swing_points
    indicators.swing_points = lambda prefix, n: ([{"type": "low", "index": 1, "price": 0, "t": 1},
                                                   {"type": "high", "index": 2, "price": 10, "t": 2}]
                                                  if len(prefix) >= 3 else [])
    try:
        result = structure.analyze_structure(candles)
        return result["trend"] == "BULLISH" and result["price_position_pct"] == 25.0
    finally:
        indicators.swing_points = original


def main():
    # Ensure the module uses the shared swing implementation, and keep test data hand-built.
    assert callable(indicators.swing_points)
    outcomes = [show("Fitil geçişi sweep, BOS değil", test_sweep_not_bos()),
                show("Gövde kapanışı BOS", test_close_is_bos()),
                show("CHoCH sonrası tek BOS trendi çevirir", test_choch_then_second_bos()),
                show("Premium/discount yüzdesi", test_premium_discount_position())]
    if not all(outcomes):
        raise SystemExit(1)
    print("test_step5: OK")


if __name__ == "__main__":
    main()
