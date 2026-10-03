"""Adım 17: tarama akışı TP1 için IRL seviyelerini signals.levels'e iletir."""
import phantom_scan
import synth


def test_irl_helper():
    from test_step15 import candle
    candles = [candle(10, 11, 9, 10, 0), candle(10, 12, 9.5, 11, 1), candle(11, 15, 10, 12, 2),
               candle(12, 13, 11, 12, 3), candle(12, 12.5, 11.5, 12, 4), candle(12, 12.2, 11.4, 12, 5),
               candle(12, 12.1, 11.5, 12, 6)]
    structure = {"range_low": 9.0, "range_high": 16.0}
    levels = phantom_scan._irl_levels(candles, structure)
    assert any(abs(level["price"] - 15.0) < 1e-9 for level in levels), levels
    assert phantom_scan._irl_levels(candles, {"range_low": None, "range_high": None}) == []
    # Aralığın dışındaki seviye IRL değildir.
    assert phantom_scan._irl_levels(candles, {"range_low": 9.0, "range_high": 14.0}) == []
    print("IRL yardımcısı (aralık içi, süpürülmemiş swing): GEÇTİ")


def test_scan_passes_irl():
    synth.isolate_dirs()
    candidates, _ = synth.scan(75)
    assert candidates, "sentetik veri aday üretmedi"
    found = 0
    for item in candidates:
        if item["tp1"] is None:
            continue
        found += 1
        assert item["tp2"] is not None
        bullish = item["direction"] == "BULLISH"
        assert (item["entry"] < item["tp1"] < item["tp2"]) if bullish else (item["entry"] > item["tp1"] > item["tp2"]), item
        assert item["rr_tp1"] >= 1.0 and item["rr_tp1"] < item["rr_tp2"], item
    assert found, "tarama akışı TP1 üretmedi: {}".format(candidates)
    print("Tarama akışında TP1 dolu ve TP1 < TP2: GEÇTİ")


def main():
    test_irl_helper()
    test_scan_passes_irl()
    print("test_step17: OK")


if __name__ == "__main__":
    main()
