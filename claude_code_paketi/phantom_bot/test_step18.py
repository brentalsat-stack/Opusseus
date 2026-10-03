"""Adım 18: puanlama OB'nin kendi zaman dilimi yapı olaylarını kullanır (1h POI ≠ 4h olayları)."""
import orderblocks
import phantom_scan


def main():
    h4_structure = {"events": [{"type": "BOS", "direction": "BULLISH", "index": 7, "marker": "4h"}]}
    h1_structure = {"events": [{"type": "BOS", "direction": "BULLISH", "index": 7, "marker": "1h"}]}
    seen = []
    originals = (orderblocks.sweep_then_bos, orderblocks.major_structure_break)
    orderblocks.sweep_then_bos = lambda ob, candles, events: seen.append(events) or False
    orderblocks.major_structure_break = lambda ob, candles, events: seen.append(events) or False
    try:
        ob = {"direction": "BULLISH", "timeframe": "1h", "low": 1.0, "high": 2.0,
              "distal": 1.0, "proximal": 2.0, "eq": 1.5, "bos_index": 7, "index": 3,
              "origin_index": 2, "state": "FRESH", "label": "DECISIONAL"}
        session = {"session_tags": [], "entry_restrictions": []}
        levels = {"entry": 2.0, "stop": 0.9, "stop_pips_or_pct": 1.0, "tp1": None, "tp2": 3.0,
                  "rr_tp1": None, "rr_tp2": 2.0, "warnings": []}
        phantom_scan._score_candidate(
            ob, "BULLISH", "BULLISH", 1, {"status": "WAITING_TAP"}, [], h4_structure,
            1.5, "crypto", session, {}, {}, [], {"range_low": 0, "range_high": 3, "protected": 0,
                                                "targeted": 3}, {"pd_valid": True, "position_pct": 40},
            levels, own_structure=h1_structure)
    finally:
        orderblocks.sweep_then_bos, orderblocks.major_structure_break = originals
    assert len(seen) == 2 and all(events[0]["marker"] == "1h" for events in seen), seen
    print("1h POI puanlaması kendi (1h) olaylarını kullanıyor: GEÇTİ")
    print("test_step18: OK")


if __name__ == "__main__":
    main()
