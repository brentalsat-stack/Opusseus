"""Adım 4 sentetik OHLC indikatör testleri; ağ erişimi kullanmaz."""
import indicators


def candle(high, low, close=None, open_=None, t=0):
    if close is None:
        close = (high + low) / 2
    if open_ is None:
        open_ = close
    return {"t": t, "o": open_, "h": high, "l": low, "c": close, "v": 1.0}


def report(name, passed):
    print("{}: {}".format(name, "GEÇTİ" if passed else "KALDI"))
    return passed


def test_bullish_fvg():
    candles = [candle(10, 8, 9, t=0), candle(11, 9, 10, t=1), candle(13, 12, 12.5, t=2)]
    fvgs = indicators.find_fvgs(candles)
    return any(fvg["type"] == "bullish" and fvg["zone_low"] == 10 and
               fvg["zone_high"] == 12 and fvg["fill_pct"] == 0 for fvg in fvgs)


def test_confirmed_swing_timing():
    candles = [candle(2, 0, t=0), candle(3, 1, t=1), candle(8, 2, t=2),
               candle(4, 1, t=3), candle(3, 0, t=4)]
    before_confirmation = indicators.swing_points(candles[:4], 2)
    after_confirmation = indicators.swing_points(candles, 2)
    high = next((point for point in after_confirmation if point["type"] == "high"), None)
    return (not any(point["type"] == "high" for point in before_confirmation) and
            high is not None and high["index"] == 2 and high["confirmation_index"] == 4)


def test_equal_highs_grouped():
    swings = [{"type": "high", "price": 1.2000, "index": 3},
              {"type": "high", "price": 1.2005, "index": 8},
              {"type": "low", "price": 1.1900, "index": 5}]
    groups = indicators.equal_levels(swings, atr_value=0.01, tol=0.1)
    return any(group["type"] == "EQH" and len(group["levels"]) == 2 for group in groups)


def main():
    outcomes = [report("Bullish FVG", test_bullish_fvg()),
                report("Swing high ve sağ mum onayı", test_confirmed_swing_timing()),
                report("EQH gruplaması", test_equal_highs_grouped())]
    if not all(outcomes):
        raise SystemExit(1)
    print("test_step4: OK")


if __name__ == "__main__":
    main()
