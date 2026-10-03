"""Adım 16: kripto risk entry proximal'dir; confirmation entry distal/EQ kuralını korur."""
import signals


def _poi(direction):
    if direction == "BULLISH":
        return {"direction": direction, "low": 100.0, "high": 110.0,
                "distal": 100.0, "proximal": 110.0, "eq": 105.0}
    return {"direction": direction, "low": 100.0, "high": 110.0,
            "distal": 110.0, "proximal": 100.0, "eq": 105.0}


def main():
    for direction, target, price in (("BULLISH", 160.0, 120.0), ("BEARISH", 50.0, 90.0)):
        poi = _poi(direction)
        risk = signals.levels(poi, market="crypto", symbol="COINUSDT", atr_value=2.0,
                              current_price=price, entry_type="risk", targeted_level=target)
        assert risk["entry"] == poi["proximal"], risk
        # Stop distal'in ötesinde, dolayısıyla risk mesafesi bölge genişliğinden küçük olamaz.
        assert risk["stop_distance"] >= abs(poi["proximal"] - poi["distal"]), risk
        expected_rr = abs(target - risk["entry"]) / risk["stop_distance"]
        assert abs(risk["rr_tp2"] - expected_rr) < 1e-9 and risk["rr_tp2"] < 10, risk

        confirmation = signals.levels(poi, market="crypto", symbol="COINUSDT", atr_value=2.0,
                                      current_price=price, entry_type="confirmation",
                                      targeted_level=target)
        assert confirmation["entry"] in (poi["distal"], poi["eq"]), confirmation
        print("Kripto risk entry proximal ({}): GEÇTİ".format(direction))
    print("test_step16: OK")


if __name__ == "__main__":
    main()
