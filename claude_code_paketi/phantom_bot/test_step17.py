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
    # Sonradan geçilmiş swing IRL olarak kalır (TP1 adayı), inducement için ise elenir.
    traded = candles + [candle(12, 16, 11, 15.5, 7), candle(15, 15.5, 14, 14.5, 8)]
    flagged = [level for level in phantom_scan._irl_levels(traded, structure)
               if abs(level["price"] - 15.0) < 1e-9]
    assert flagged and flagged[0]["swept"] is True, flagged
    assert not any(abs(level["price"] - 15.0) < 1e-9 for level in phantom_scan._liquidity_levels(traded))
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


def test_tp1_prefers_unswept():
    import signals
    poi = {"direction": "BULLISH", "low": 99.0, "high": 100.0, "distal": 99.0,
           "proximal": 100.0, "eq": 99.5}
    kwargs = dict(market="crypto", symbol="COINUSDT", atr_value=0.1, current_price=110.0,
                  entry_type="risk", targeted_level=130.0)
    swept_near = {"price": 105.0, "swept": True}
    unswept_far = {"price": 115.0, "swept": False}
    result = signals.levels(poi, irl_levels=[swept_near, unswept_far], **kwargs)
    assert result["tp1"] == 115.0 and "TP1_SWEPT_LEVEL" not in result["warnings"], result
    result = signals.levels(poi, irl_levels=[swept_near], **kwargs)
    assert result["tp1"] == 105.0 and "TP1_SWEPT_LEVEL" in result["warnings"], result
    assert result["tp1"] < result["tp2"] and result["rr_tp1"] >= 1.0
    # Düz fiyat listeleri (eski çağrılar) süpürülmemiş sayılır.
    result = signals.levels(poi, irl_levels=[105.0], **kwargs)
    assert result["tp1"] == 105.0 and "TP1_SWEPT_LEVEL" not in result["warnings"]
    # 1R altındaki süpürülmemiş seviye geçerli değil, süpürülmüş uygun olana düşülür.
    close_unswept = {"price": 100.2, "swept": False}
    result = signals.levels(poi, irl_levels=[close_unswept, swept_near], **kwargs)
    assert result["tp1"] == 105.0 and "TP1_SWEPT_LEVEL" in result["warnings"], result
    # Hiç uygun seviye yoksa TP1 boş kalır.
    assert signals.levels(poi, irl_levels=[], **kwargs)["tp1"] is None
    # Bearish simetrik.
    bear = {"direction": "BEARISH", "low": 100.0, "high": 101.0, "distal": 101.0,
            "proximal": 100.0, "eq": 100.5}
    result = signals.levels(bear, market="crypto", symbol="COINUSDT", atr_value=0.1,
                            current_price=90.0, entry_type="risk", targeted_level=70.0,
                            irl_levels=[{"price": 95.0, "swept": True}])
    assert result["tp1"] == 95.0 and "TP1_SWEPT_LEVEL" in result["warnings"], result
    print("TP1: önce süpürülmemiş IRL, yoksa süpürülmüş + TP1_SWEPT_LEVEL: GEÇTİ")


def main():
    test_tp1_prefers_unswept()
    test_irl_helper()
    test_scan_passes_irl()
    print("test_step17: OK")


if __name__ == "__main__":
    main()
