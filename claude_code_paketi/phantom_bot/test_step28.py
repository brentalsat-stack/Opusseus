"""Adım 28: karşı-trend cezası yalnız 4h bias açıkça ters yöndeyse; UNDEFINED ceza almaz."""
import phantom_scan


def breakdown(direction, bias_d1, bias_h4):
    ob = {"direction": direction, "timeframe": "4h", "low": 1.0, "high": 2.0, "distal": 1.0,
          "proximal": 2.0, "eq": 1.5, "bos_index": 7, "index": 3, "origin_index": 2,
          "state": "FRESH", "label": "DECISIONAL"}
    levels = {"entry": 2.0, "stop": 0.9, "stop_pips_or_pct": 1.0, "tp1": None, "tp2": 3.0,
              "rr_tp1": None, "rr_tp2": 2.0, "warnings": []}
    result = phantom_scan._score_candidate(
        ob, bias_d1, bias_h4, 1, {"status": "WAITING_TAP"}, [], {"events": []}, 1.5, "crypto",
        {"session_tags": [], "entry_restrictions": []}, {}, {}, [],
        {"range_low": 0, "range_high": 3, "protected": 0, "targeted": 3},
        {"pd_valid": True, "position_pct": 40}, levels)
    return {row["criterion"] for row in result["score_breakdown"]}


def main():
    for direction, same, opposite in (("BULLISH", "BULLISH", "BEARISH"), ("BEARISH", "BEARISH", "BULLISH")):
        assert "counter_trend_penalty" in breakdown(direction, same, opposite)
        assert "counter_trend_penalty" in breakdown(direction, opposite, opposite)
        assert "counter_trend_penalty" not in breakdown(direction, same, "UNDEFINED")
        assert "counter_trend_penalty" not in breakdown(direction, opposite, "UNDEFINED")
        assert "counter_trend_penalty" not in breakdown(direction, "UNDEFINED", same)
        assert "counter_trend_penalty" not in breakdown(direction, opposite, same)  # D1 ters ama 4h aynı
        # +20 HTF uyumu hâlâ iki zaman diliminin de aynı yönde olmasını ister.
        assert "htf_alignment" in breakdown(direction, same, same)
        assert "htf_alignment" not in breakdown(direction, "UNDEFINED", same)
    print("Karşı-trend yalnız 4h açıkça ters olduğunda: GEÇTİ")
    print("test_step28: OK")


if __name__ == "__main__":
    main()
