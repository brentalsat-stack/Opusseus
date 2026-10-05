"""Adım 26: confirmation entry LTF OB'den; risk entry 15m'e rafine OB'nin proximal'inden."""
import phantom_scan
import signals
import synth
from test_step15 import candle


def test_ltf_ob_from_bos():
    poi = {"direction": "BULLISH", "low": 100.0, "high": 101.0, "distal": 100.0,
           "proximal": 101.0, "eq": 100.5}
    # Dokunuş (100.5), düşüş bacağı, ardından son bearish mum (index 5) ve BOS (index 8).
    candles = [candle(103, 104, 102, 103, 0), candle(103, 103.5, 100.4, 101, 1),
               candle(101, 102, 100.8, 101.5, 2), candle(101.5, 103, 101, 102.5, 3),
               candle(102.5, 103.2, 101.8, 102.0, 4), candle(102.0, 102.2, 100.6, 100.8, 5),
               candle(100.8, 101.9, 100.7, 101.8, 6), candle(101.8, 102.6, 101.5, 102.4, 7),
               candle(102.4, 105.0, 102.3, 104.8, 8), candle(104.8, 105.5, 104.2, 105.2, 9),
               candle(105.2, 105.6, 104.9, 105.3, 10)]
    status = signals.ltf_status(poi, candles, [], 3)
    assert status["status"] == "ENTRY1_READY", status
    ob = status["ltf_ob"]
    assert ob and ob["tf"] == "15m" and ob["index"] == 5, ob
    assert (ob["high"], ob["low"]) == (102.2, 100.6) and ob["proximal"] == 102.2 and ob["distal"] == 100.6
    assert signals.ltf_status(poi, candles[:3], [], 3)["ltf_ob"] is None
    print("LTF OB, BOS'u üreten bacağın origin'indeki son karşıt mum: GEÇTİ")


def test_levels_use_ltf_ob():
    poi = {"direction": "BULLISH", "low": 90.0, "high": 110.0, "distal": 90.0,
           "proximal": 110.0, "eq": 100.0}
    ltf_ob = {"high": 102.2, "low": 100.6, "proximal": 102.2, "distal": 100.6, "eq": 101.4}
    for entry_type in ("confirmation", "double_confirmation"):
        result = signals.levels(poi, market="forex", symbol="EUR/USD", spread_pips=0.8,
                                entry_type=entry_type, ltf_ob=ltf_ob, current_price=104.0,
                                targeted_level=130.0)
        assert result["entry"] in (100.6, 101.4), result
        assert result["stop"] < 100.6 and result["stop"] > poi["distal"], result
        assert result["entry_type"] == entry_type
    risk = signals.levels(poi, market="forex", symbol="EUR/USD", entry_type="risk",
                          current_price=104.0, targeted_level=130.0)
    assert risk["entry"] == 110.0
    print("Seviyeler LTF OB'ye göre (giriş distal/EQ, stop LTF distal ötesi): GEÇTİ")


def test_refine():
    htf = [candle(100, 101, 99, 100, 1000 + i * 3600) for i in range(5)]
    ob = {"direction": "BULLISH", "timeframe": "1h", "index": 2, "low": 99.0, "high": 101.0}
    base = 1000 + 2 * 3600
    m15 = [candle(100, 100.5, 99.5, 100, base + i * 900) for i in range(4)] + \
          [candle(100, 100.5, 99.5, 100, base + 4 * 900)]
    inside_early = {"direction": "BULLISH", "index": 0, "low": 99.2, "high": 100.0,
                    "proximal": 100.0, "distal": 99.2, "eq": 99.6}
    inside_late = {"direction": "BULLISH", "index": 2, "low": 99.4, "high": 99.9,
                   "proximal": 99.9, "distal": 99.4, "eq": 99.65}
    too_wide = {"direction": "BULLISH", "index": 3, "low": 98.0, "high": 100.0,
                "proximal": 100.0, "distal": 98.0, "eq": 99.0}
    outside_span = {"direction": "BULLISH", "index": 4, "low": 99.3, "high": 99.8,
                    "proximal": 99.8, "distal": 99.3, "eq": 99.55}
    wrong_side = dict(inside_late, direction="BEARISH")
    refined = phantom_scan._refine_poi(ob, htf, m15, [inside_early, inside_late, too_wide,
                                                      outside_span, wrong_side])
    assert refined["proximal"] == 99.9 and refined["distal"] == 99.4, refined
    assert phantom_scan._refine_poi(ob, htf, m15, [too_wide, outside_span, wrong_side]) is None
    print("15m rafine: aynı yön, HTF mumunun içinde, bölgenin içinde, en yeni: GEÇTİ")


def test_scan_uses_ltf_entry():
    synth.isolate_dirs()
    forced = {"status": "ENTRY2_READY", "ltf_tf": "5m", "entry_restriction": "",
              "bos_counts": {"15m": 0, "5m": 2}, "bos_events": {"15m": [], "5m": []}}
    original = signals.ltf_status

    def fake(poi, *args, **kwargs):
        result = dict(forced)
        result["ltf_ob"] = {"tf": "5m", "high": poi["proximal"], "low": poi["proximal"] * 0.999,
                            "proximal": poi["proximal"], "distal": poi["proximal"] * 0.999,
                            "eq": poi["proximal"] * 0.9995}
        return result

    signals.ltf_status = fake
    try:
        candidates, _ = synth.scan(75)
    finally:
        signals.ltf_status = original
    assert candidates
    for item in candidates:
        assert item["entry_type"] == "double_confirmation" and item["status"] == "ENTRY2_READY", item
        assert item["ltf_ob"]["tf"] == "5m"
        assert item["stop"] < item["entry"] and item["entry"] <= item["ltf_ob"]["high"], item
    print("Tarama akışı ENTRY2_READY'de LTF OB girişini kullanıyor: GEÇTİ")


def main():
    test_ltf_ob_from_bos()
    test_levels_use_ltf_ob()
    test_refine()
    test_scan_uses_ltf_entry()
    print("test_step26: OK")


if __name__ == "__main__":
    main()
