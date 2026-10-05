"""Adım 6 elle kurulmuş order block testleri."""
import orderblocks


def candle(open_, high, low, close, t):
    return {"t": t, "o": float(open_), "h": float(high), "l": float(low), "c": float(close), "v": 1.0}


def report(name, passed):
    print("{}: {}".format(name, "GEÇTİ" if passed else "KALDI"))
    return passed


def test_ob_candle_and_refinement():
    candles = [
        candle(10, 11, 9, 10, 0),       # bearish OB adayının solundaki mum
        candle(10, 10.5, 8, 8.5, 1),    # son bearish mum / OB
        candle(8.5, 9, 8, 8.2, 2),      # karşıt mum adayı
        candle(8.1, 9, 8, 8.7, 3),      # ara yükseliş; kapanış OB üstünü aşmaz
        candle(8, 17, 8, 17, 4),        # güçlü bullish displacement
        candle(17, 18, 16, 17.5, 5),    # BOS
    ]
    result = {"events": [{"type": "BOS", "direction": "BULLISH", "index": 5, "origin_index": 0}]}
    blocks = orderblocks.find_order_blocks(candles, result)
    # The last bearish candle is index 2; because its next close does not
    # clear its high, refinement moves forward to the candle immediately before
    # the momentum (displacement) candle 4, i.e. index 3.
    return bool(blocks) and blocks[0]["index"] == 3 and blocks[0]["displacement_index"] == 4


def test_distal_close_invalid():
    ob = {"direction": "BULLISH", "high": 10.0, "low": 8.0, "eq": 9.0,
          "distal": 8.0, "bos_index": -1}
    candles = [candle(9, 9.5, 7.5, 7.9, 1)]
    return orderblocks.evaluate_ob_state(ob, candles)["state"] == "INVALID"


def test_stacking_counts():
    d1 = [{"direction": "BULLISH", "low": 9.0, "high": 12.0}]
    h4 = [{"direction": "BULLISH", "low": 10.0, "high": 11.0}]
    h1 = [{"direction": "BULLISH", "low": 10.5, "high": 10.8}]
    stacked = orderblocks.stack_obs(d1, h4, h1)
    counts = [ob["stack_count"] for ob in stacked]
    return len(stacked) == 2 and counts == [3, 3]


def main():
    outcomes = [report("OB mumu ve rafine", test_ob_candle_and_refinement()),
                report("Distal ötesi gövde kapanışı INVALID", test_distal_close_invalid()),
                report("TF stacking çakışma sayısı", test_stacking_counts())]
    if not all(outcomes):
        raise SystemExit(1)
    print("test_step6: OK")


if __name__ == "__main__":
    main()
