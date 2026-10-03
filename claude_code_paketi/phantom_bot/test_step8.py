"""Adım 8 synthetic state and level calculation checks."""
import signals


def candle(open_, high, low, close, t):
    return {"t": t, "o": float(open_), "h": float(high), "l": float(low), "c": float(close), "v": 1.0}


def main():
    poi = {"direction": "BULLISH", "low": 1.1000, "high": 1.1010,
           "distal": 1.1000, "proximal": 1.1010, "eq": 1.1005}
    waiting = signals.ltf_status(poi, [candle(1.102, 1.103, 1.102, 1.1025, 0)], [], 3)
    tapped = signals.ltf_status(poi, [candle(1.102, 1.1025, 1.1005, 1.101, 0)], [], 3)
    invalid = signals.ltf_status(poi, [candle(1.102, 1.1025, 1.099, 1.0995, 0)], [], 3)
    assert waiting["status"] == "WAITING_TAP"
    assert tapped["status"] == "TAPPED_NO_BOS"
    assert invalid["status"] == "INVALIDATED"
    restricted = signals.ltf_status(poi, [], [], 3, {"asia": True, "news": True})
    assert restricted["status"] == "WAITING_TAP" and restricted["entry_restriction"] == "ASIA,NEWS"
    print("LTF durumları:", waiting["status"], "->", tapped["status"], "->", invalid["status"])
    print("Giriş kısıtı:", restricted["entry_restriction"], "(STATUS:", restricted["status"] + ")")

    calculated = signals.levels(poi, market="forex", symbol="EUR/USD",
                                entry_type="confirmation", spread_pips=0.8,
                                irl_levels=[1.1020, 1.1040], targeted_level=1.1100,
                                current_price=1.1010)
    assert calculated["entry"] == poi["distal"]
    assert calculated["tp1"] == 1.1020 and calculated["tp2"] == 1.1100
    assert calculated["rr_tp2"] is not None
    print("Seviyeler:", calculated)

    crypto = signals.levels({"direction": "BULLISH", "low": 100.0, "high": 102.0,
                             "distal": 100.0, "proximal": 102.0, "eq": 101.0},
                            market="crypto", symbol="BTCUSDT", atr_value=2.0,
                            irl_levels=[105.0], targeted_level=110.0,
                            entry_type="confirmation")
    assert crypto["stop_unit"] == "pct" and crypto["tp2"] == 110.0
    print("Kripto seviyeleri:", crypto)
    print("test_step8: OK")


if __name__ == "__main__":
    main()
