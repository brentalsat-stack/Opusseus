"""Synthetic checks for order-block score features added in step 14."""
import orderblocks


def candle(open_, high, low, close, t):
    return {"t": t, "o": float(open_), "h": float(high),
            "l": float(low), "c": float(close), "v": 1.0}


def test_return_profiles():
    base = [candle(100, 101, 99, 100, i) for i in range(14)]
    v_candles = base + [
        candle(100, 101, 99, 100.5, 14),
        candle(102, 110, 101, 109, 15),
        candle(109, 109, 89, 96, 16),
    ]
    poi = {"direction": "BULLISH", "low": 90, "high": 91,
           "distal": 90, "proximal": 91, "bos_index": 14}
    v_result = orderblocks.return_profile(poi, v_candles)
    assert v_result["v_reversal_penalty"] is True, v_result
    assert v_result["corrective_return"] is False, v_result

    corrective_candles = base + [
        candle(100, 101, 99, 100.5, 14),
        candle(100, 110, 99, 100.5, 15),
        candle(100.5, 102, 98, 100, 16),
        candle(100, 101, 96, 99.5, 17),
        candle(99.5, 100, 95, 99, 18),
        candle(99, 100, 89, 98.5, 19),
    ]
    corrective_result = orderblocks.return_profile(poi, corrective_candles)
    assert corrective_result["corrective_return"] is True, corrective_result
    assert corrective_result["v_reversal_penalty"] is False, corrective_result

    no_touch_candles = base + [
        candle(100, 101, 99, 100.5, 14),
        candle(100, 110, 99, 109, 15),
    ]
    no_touch_result = orderblocks.return_profile(poi, no_touch_candles)
    assert no_touch_result["poi_touched"] is False, no_touch_result
    assert no_touch_result["return_leg_candles"] == 0, no_touch_result
    assert no_touch_result["v_reversal_penalty"] is False, no_touch_result
    assert no_touch_result["corrective_return"] is False, no_touch_result
    print("Dönüş profilleri: V ve corrective GEÇTİ")
    print("OB dokunulmadan son mumda itki: V cezası yok GEÇTİ")


def test_sweep_order():
    candles = [
        candle(9, 10, 8, 9, 0), candle(8, 9, 7, 8, 1),
        candle(7, 8, 5, 6, 2), candle(6, 9, 7, 8, 3),
        candle(8, 9, 7.5, 8.5, 4), candle(8, 9, 4.5, 8.2, 5),
        candle(8.2, 9, 7.5, 8.5, 6), candle(8.5, 9, 8, 8.7, 7),
        candle(8.7, 10, 8.5, 9.8, 8),
    ]
    ob = {"direction": "BULLISH", "origin_index": 7, "bos_index": 8}
    sweep = {"type": "LIQUIDITY_SWEEP", "direction": "BEARISH",
             "index": 5, "swing_index": 2}
    bos = {"type": "BOS", "direction": "BULLISH", "index": 8,
           "origin_index": 7, "level": 9.5, "swing_index": 4}
    assert orderblocks.sweep_then_bos(ob, candles, [sweep, bos], lookback=2) is True
    after_bos = dict(sweep, index=8)
    assert orderblocks.sweep_then_bos(ob, candles, [after_bos, bos], lookback=2) is False
    before_window = dict(sweep, index=4)
    assert orderblocks.sweep_then_bos(ob, candles, [before_window, bos], lookback=2) is False
    wrong_side = dict(sweep, direction="BULLISH")
    assert orderblocks.sweep_then_bos(ob, candles, [wrong_side, bos], lookback=2) is False
    print("Sweep sonra BOS sırası ve yönü: GEÇTİ")


def test_major_minor():
    major_candles = [candle(10, 12, 9, 11, i) for i in range(13)]
    major_candles[5] = candle(12, 20, 11, 15, 5)
    major = {"direction": "BULLISH", "bos_index": 12}
    major_event = {"type": "BOS", "direction": "BULLISH", "index": 12,
                   "swing_index": 5, "level": 20}
    assert orderblocks.major_structure_break(major, major_candles, [major_event]) is True

    minor_candles = [candle(10, 12, 9, 11, i) for i in range(13)]
    minor_candles[1] = candle(12, 25, 11, 15, 1)
    minor_candles[5] = candle(12, 20, 11, 15, 5)
    minor = {"direction": "BULLISH", "bos_index": 12}
    minor_event = dict(major_event)
    assert orderblocks.major_structure_break(minor, minor_candles, [minor_event]) is False
    print("Majör/minör swing ayrımı: GEÇTİ")


def test_left_zone_mitigation():
    candles = [candle(10, 12, 9, 11, i) for i in range(5)]
    older = {"direction": "BULLISH", "bos_index": 1,
             "low": 9.5, "high": 10.5}
    newer = {"direction": "BULLISH", "origin_index": 2, "bos_index": 4}
    assert orderblocks.mitigated_left_zone(newer, candles, [older]) is True
    print("Önceki OB bölgesine dönüş: GEÇTİ")


def main():
    test_return_profiles()
    test_sweep_order()
    test_major_minor()
    test_left_zone_mitigation()
    print("test_step14: OK")


if __name__ == "__main__":
    main()
