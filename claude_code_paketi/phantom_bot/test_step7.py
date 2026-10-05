"""Adım 7 sentetik likidite testleri ve New York seans örnekleri."""
from datetime import datetime, timezone

import liquidity
import sessions


def candle(high, low, close, t):
    return {"t": t, "o": close, "h": high, "l": low, "c": close, "v": 1.0}


def main():
    # London seansı 03:00 New York: kış UTC-5 -> 08:00 UTC; yaz UTC-4 -> 07:00 UTC.
    examples = [
        ("Kış London", datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)),
        ("Yaz London", datetime(2026, 7, 15, 7, 0, tzinfo=timezone.utc)),
        ("Kış Asya", datetime(2026, 1, 16, 1, 0, tzinfo=timezone.utc)),
        ("Yaz Asya", datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc)),
    ]
    for name, timestamp in examples:
        print("{} — {} NY — {}".format(name, sessions.utils.utc_to_new_york(timestamp).strftime("%Y-%m-%d %H:%M"),
                                        ",".join(sessions.session_tags(timestamp)) or "aktif seans yok"))

    # Swing-high liquidity above 10 is swept by a wick and rejected by close.
    candles = [candle(10.5, 9.0, 9.8, 1)]
    sweeps = liquidity.detect_sweeps(candles, [{"type": "EQH", "price": 10.0}])
    assert len(sweeps) == 1 and sweeps[0]["direction"] == "BEARISH"
    print("Sweep tespiti: GEÇTİ —", sweeps[0])

    poi = {"direction": "BULLISH", "low": 9.0, "high": 10.0}
    levels = [{"type": "EQL", "price": 8.5},    # POI'nin altında: inducement değil
              {"type": "EQL", "price": 11.5},   # POI ile fiyat arasında: geçerli
              {"type": "low", "price": 12.5},   # daha uzak swing low
              {"type": "EQL", "price": 15.0},   # fiyatın üstünde: geçerli değil
              {"type": "EQH", "price": 11.0}]   # yanlış tür
    inducement = liquidity.find_inducement(poi, "BULLISH", levels, current_price=14.0)
    assert inducement is not None and inducement["price"] == 11.5
    assert liquidity.find_inducement(poi, "BULLISH", [{"type": "EQL", "price": 8.5}], current_price=14.0) is None
    bear = {"direction": "BEARISH", "low": 20.0, "high": 21.0}
    bear_levels = [{"type": "EQH", "price": 21.5}, {"type": "EQH", "price": 17.0},
                   {"type": "high", "price": 18.5}, {"type": "EQH", "price": 14.0}]
    bearish = liquidity.find_inducement(bear, "BEARISH", bear_levels, current_price=15.0)
    assert bearish is not None and bearish["price"] == 18.5
    inducement = inducement
    print("Inducement tespiti: GEÇTİ —", inducement)
    print("test_step7: OK")


if __name__ == "__main__":
    main()
