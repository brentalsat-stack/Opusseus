"""Regression check for an already-tapped HTF POI with later LTF BOS events."""
import signals


def candle(open_, high, low, close, t):
    return {"t": t, "o": float(open_), "h": float(high),
            "l": float(low), "c": float(close), "v": 1.0}


def main():
    poi = {"direction": "BULLISH", "low": 1.1000, "high": 1.1010,
           "distal": 1.1000, "proximal": 1.1010, "eq": 1.1005}

    # No LTF candle intersects the POI. Two later body closes break confirmed
    # swing highs, each with a bearish origin candle between BOS events.
    candles_15m = [
        candle(1.1020, 1.1030, 1.1015, 1.1025, 0),
        candle(1.1025, 1.1040, 1.1020, 1.1030, 1),
        candle(1.1030, 1.1050, 1.1025, 1.1040, 2),
        candle(1.1040, 1.1045, 1.1025, 1.1035, 3),
        candle(1.1035, 1.1040, 1.1020, 1.1025, 4),
        candle(1.1040, 1.1070, 1.1035, 1.1060, 5),
        candle(1.1060, 1.1075, 1.1040, 1.1050, 6),
        candle(1.1060, 1.1100, 1.1055, 1.1090, 7),
        candle(1.1090, 1.1095, 1.1060, 1.1070, 8),
        candle(1.1070, 1.1090, 1.1040, 1.1050, 9),
        candle(1.1080, 1.1120, 1.1075, 1.1110, 10),
    ]
    result = signals.ltf_status(
        poi, candles_15m, [], stack_count=3, htf_state="TAPPED")

    assert result["bos_counts"]["15m"] >= 2, result
    assert result["status"] == "ENTRY2_READY", result
    print("HTF TAPPED, LTF dokunuş yok, iki BOS:", result["status"])
    print("BOS sayıları:", result["bos_counts"])
    print("test_step13: OK")


if __name__ == "__main__":
    main()
