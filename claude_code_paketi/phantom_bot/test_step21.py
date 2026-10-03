"""Adım 21: inducement POI ile fiyat arasındaki likiditedir; EQH/EQL tarama seviyelerinde bulunur."""
import liquidity
import phantom_scan
from test_step15 import candle


def main():
    # Bullish: fiyat 14, POI 9-10, aradaki EQL 11.5 inducement olur; POI altındaki olmaz.
    poi = {"low": 9.0, "high": 10.0}
    assert liquidity.find_inducement(poi, "BULLISH", [{"type": "EQL", "price": 11.5}], 14.0)["price"] == 11.5
    assert liquidity.find_inducement(poi, "BULLISH", [{"type": "EQL", "price": 8.0}], 14.0) is None
    assert liquidity.find_inducement(poi, "BULLISH", [{"type": "EQL", "price": 11.5}], None) is None
    # Bearish simetrik: POI 20-21, fiyat 15, aradaki EQH 18 inducement olur.
    bear = {"low": 20.0, "high": 21.0}
    assert liquidity.find_inducement(bear, "BEARISH", [{"type": "EQH", "price": 18.0}], 15.0)["price"] == 18.0
    assert liquidity.find_inducement(bear, "BEARISH", [{"type": "EQH", "price": 22.0}], 15.0) is None

    # _liquidity_levels: iki eşit swing low EQL grubu üretir; süpürülmüş seviye elenir.
    lows = [11, 10, 8, 10, 12, 10, 8.005, 10, 12, 10, 13, 12.5, 13.5, 14, 13.8, 14.2]
    candles = [candle(l + 1, l + 2, l, l + 1.5, i) for i, l in enumerate(lows)]
    levels = phantom_scan._liquidity_levels(candles)
    types = {level["type"] for level in levels}
    assert "EQL" in types and "low" in types, levels
    swept = candles + [candle(9, 9, 5, 6, 99), candle(6, 7, 5.5, 6, 100)]
    swept_levels = phantom_scan._liquidity_levels(swept)
    assert not any(level["type"] == "low" and level["price"] in (8, 8.005) for level in swept_levels), swept_levels
    print("Inducement yönü (bullish/bearish), EQL grubu ve süpürülmüş seviye: GEÇTİ")
    print("test_step21: OK")


if __name__ == "__main__":
    main()
