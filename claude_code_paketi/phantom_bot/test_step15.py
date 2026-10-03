"""Offline regression tests for target selection, filters and report rules."""
import config
import phantom_scan
import report
import signals


def candle(open_, high, low, close, t):
    return {"t": t, "o": float(open_), "h": float(high),
            "l": float(low), "c": float(close), "v": 1.0}


def test_targets():
    poi = {"direction": "BULLISH", "low": 0.42, "high": 0.43,
           "distal": 0.42, "proximal": 0.43, "eq": 0.425}
    result = signals.levels(
        poi, market="crypto", symbol="WLDUSDT", atr_value=0.01,
        current_price=0.44, entry_type="risk", targeted_level=0.46,
        irl_levels=[0.421, 0.425, 0.46, 0.45])
    assert result["tp2"] == 0.46, result
    assert result["tp2"] > max(result["entry"], 0.44), result
    assert result["tp1"] is not None and result["tp1"] < result["tp2"], result
    assert result["rr_tp1"] >= 1.0, result

    fallback = signals.levels(
        poi, market="crypto", symbol="WLDUSDT", atr_value=0.01,
        current_price=0.44, targeted_level=0.439,
        pd_levels={"PDH": 0.45}, pw_levels={"PWH": 0.50})
    assert fallback["tp2"] == 0.45, fallback
    no_target = signals.levels(
        poi, market="crypto", symbol="WLDUSDT", atr_value=0.01,
        current_price=0.44, targeted_level=0.439,
        pd_levels={"PDH": 0.43}, pw_levels={"PWH": 0.44})
    assert no_target["tp2"] is None and "NO_TARGET" in no_target["warnings"], no_target
    print("TP1/TP2, hedefin güncel fiyat ötesinde olması ve fallback: GEÇTİ")


def test_poi_filters():
    h4 = {"trend": "BULLISH", "range_low": 90.0, "range_high": 110.0,
          "protected": {"type": "low", "price": 92.0},
          "targeted": {"type": "high", "price": 108.0}}
    context = phantom_scan._active_context("BULLISH", h4)
    inside_discount = {"direction": "BULLISH", "low": 93.0, "high": 95.0,
                       "distal": 93.0, "proximal": 95.0, "eq": 94.0}
    location = phantom_scan._poi_location(inside_discount, "BULLISH", context)
    assert location["pd_valid"] is True and location["range_valid"] is True, location

    wrong_pd = dict(inside_discount, eq=105.0)
    wrong_location = phantom_scan._poi_location(wrong_pd, "BULLISH", context)
    assert wrong_location["pd_valid"] is False, wrong_location

    outside = dict(inside_discount, low=89.0, distal=89.0)
    outside_location = phantom_scan._poi_location(outside, "BULLISH", context)
    assert outside_location["range_valid"] is False, outside_location

    opposing_context = phantom_scan._active_context(
        "BULLISH", dict(h4, trend="BEARISH", protected={"price": 100},
                        targeted={"price": 95}))
    assert opposing_context["protected"] == 90.0
    assert opposing_context["targeted"] == 110.0
    print("POI PD/aralık filtreleri ve 4h range fallback: GEÇTİ")


def test_distance_and_report_rules():
    daily = [candle(100, 101, 99, 100, i) for i in range(20)]
    allowed, atr_value, _ = phantom_scan._distance_filter(105, 100, daily)
    assert allowed is True and atr_value == 2.0
    allowed, _, distance = phantom_scan._distance_filter(107, 100, daily)
    assert allowed is False and distance == 7.0

    assert report._format_price(1.1234567, "forex", "EUR/USD") == 1.12346
    assert report._format_price(150.1239, "forex", "USD/JPY") == 150.124
    assert report._format_price(2300.1239, "forex", "XAU/USD") == 2300.124
    assert report._format_price(0.00012345678, "crypto", "COINUSDT") == 0.000123457
    assert report._format_price(1234567.0, "crypto", "COINUSDT") == 1234570.0

    good = {"grade": "A", "rr_tp2": 5.0, "tp2": 1.2, "warnings": []}
    blocked = {"grade": "B", "rr_tp2": 8.0, "tp2": None, "warnings": ["NO_TARGET"]}
    assert report._qualifies_ab(good) is True
    assert report._qualifies_ab(blocked) is False
    print("Günlük ATR mesafe filtresi ve rapor koşulları: GEÇTİ")


def main():
    assert config.MAX_POI_DISTANCE_ATR_D1 == 3.0
    test_targets()
    test_poi_filters()
    test_distance_and_report_rules()
    print("test_step15: OK")


if __name__ == "__main__":
    main()
