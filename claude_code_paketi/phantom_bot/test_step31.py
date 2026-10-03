"""Adım 31: CHoCH ilk kırılım sayılır, tek BOS trendi çevirir; OB rafinesi momentum mumunun öncesine kayar."""
import indicators
import orderblocks
import structure
from test_step5 import candle


def with_swings(swing_rows, candles):
    original = indicators.swing_points

    def fake(prefix, n):
        return [dict(row) for row in swing_rows if row["index"] + 2 < len(prefix) + 1 and row["conf"] <= len(prefix) - 1]

    indicators.swing_points = fake
    try:
        return structure.analyze_structure(candles)
    finally:
        indicators.swing_points = original


def test_choch_plus_one_bos():
    # Uptrend: HL 5 (index1), HH 10 (index2) kırılır; protected low 4 (index5) kırılınca CHoCH;
    # swing low 3 (index7) kırılınca TEK BOS trendi BEARISH yapar.
    candles = [candle(7, 8, 6, 7, 0), candle(7, 8, 5, 7, 1), candle(9, 10, 4, 9, 2),
               candle(8, 9, 4.5, 8, 3), candle(11, 12, 6, 11, 4), candle(4, 5, 3.5, 4, 5),
               candle(5, 6, 4.5, 5, 6), candle(3.5, 4, 3, 3.5, 7), candle(4, 5, 3.5, 4, 8),
               candle(2.5, 3, 2, 2.5, 9)]
    rows = [{"type": "low", "index": 1, "price": 5, "t": 1, "conf": 2},
            {"type": "high", "index": 2, "price": 10, "t": 2, "conf": 3},
            {"type": "low", "index": 5, "price": 4, "t": 5, "conf": 7},
            {"type": "low", "index": 7, "price": 3, "t": 7, "conf": 9}]
    original = indicators.swing_points
    indicators.swing_points = lambda prefix, n: [
        dict(row) for row in rows if row["conf"] <= len(prefix) - 1 or
        (row["index"] == 1 and len(prefix) >= 3) or (row["index"] == 2 and len(prefix) >= 3) or
        (row["index"] == 5 and len(prefix) >= 8) or (row["index"] == 7 and len(prefix) >= 10)]
    try:
        events = structure.analyze_structure(candles)["events"]
        choch = next(event for event in events if event["type"] == "CHoCH")
        after_choch = structure.analyze_structure(candles[:choch["index"] + 1])
        assert after_choch["trend"] == "CHOCH_BEARISH", after_choch["trend"]
        confirmation = next(event for event in events if event["type"] == "BOS_CONFIRMATION")
        assert confirmation["direction"] == "BEARISH" and confirmation["index"] > choch["index"]
        confirmed = structure.analyze_structure(candles[:confirmation["index"] + 1])
        assert confirmed["trend"] == "BEARISH", confirmed["trend"]
    finally:
        indicators.swing_points = original
    print("CHoCH ilk kırılım, ardından 1 BOS trendi çevirir: GEÇTİ")


def test_ob_refinement_moves_before_momentum():
    # index 1: OB adayı (bearish) — sonraki mum (index 2) kapanışı OB high'ının üstüne çıkmıyor;
    # momentum mumu index 3: rafine OB, onun hemen öncesindeki mum (index 2).
    candles = [candle(10.5, 10.6, 9.4, 9.5, 0),   # bearish (rafine hedef)
               candle(9.6, 9.8, 9.2, 9.3, 1),     # bearish, OB adayı; sonraki mum bunu kırmıyor
               candle(9.3, 9.7, 9.2, 9.6, 2),     # zayıf mum: kapanış 9.6 <= OB high 9.8
               candle(9.6, 12.5, 9.5, 12.4, 3)]   # momentum + BOS
    events = [{"type": "BOS", "direction": "BULLISH", "index": 3, "origin_index": 0, "level": 10.0,
               "swing_index": 0}]
    blocks = orderblocks.find_order_blocks(candles, {"events": events}, "1h")
    assert blocks and blocks[0]["index"] == 2, blocks
    print("OB rafinesi: momentum mumunun hemen öncesindeki muma kayıyor: GEÇTİ")


def test_ob_refinement_not_applied_when_next_candle_clears():
    candles = [candle(10.5, 10.6, 9.4, 9.5, 0), candle(9.6, 9.8, 9.2, 9.3, 1),
               candle(9.3, 10.4, 9.2, 10.2, 2),  # sonraki mum OB high'ını (9.8) kapanışla aşıyor
               candle(10.2, 12.5, 10.1, 12.4, 3)]
    events = [{"type": "BOS", "direction": "BULLISH", "index": 3, "origin_index": 0, "level": 10.0,
               "swing_index": 0}]
    blocks = orderblocks.find_order_blocks(candles, {"events": events}, "1h")
    assert blocks and blocks[0]["index"] == 1, blocks
    print("Sonraki mum OB'yi kırıyorsa rafine yok: GEÇTİ")


def main():
    test_choch_plus_one_bos()
    test_ob_refinement_moves_before_momentum()
    test_ob_refinement_not_applied_when_next_candle_clears()
    print("test_step31: OK")


if __name__ == "__main__":
    main()
