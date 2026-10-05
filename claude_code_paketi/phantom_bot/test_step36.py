"""Adım 36: temizlik — --top 30–40 sınırı, REQUIRE_FVG_FOR_OB, kullanılmayan ayarların kalkması."""
import re

import config
import orderblocks
import phantom_scan
from test_step15 import candle


def test_top_bounds():
    import contextlib, io
    quiet = io.StringIO()
    assert phantom_scan.parse_args(["--market", "crypto", "--top", "30"]).top == 30
    assert phantom_scan.parse_args(["--market", "crypto", "--top", "40"]).top == 40
    assert phantom_scan.parse_args(["--market", "crypto"]).top == config.CRYPTO_TOP_DEFAULT
    for bad in ("29", "41", "5"):
        try:
            with contextlib.redirect_stderr(quiet):
                phantom_scan.parse_args(["--market", "crypto", "--top", bad])
        except SystemExit:
            continue
        raise AssertionError("--top {} reddedilmeliydi".format(bad))
    print("--top yalnız 30–40: GEÇTİ")


def test_require_fvg():
    # Bacakta FVG yok: iç içe örtüşen mumlar.
    candles = [candle(10, 10.5, 9.4, 9.5, 0), candle(9.5, 10.2, 9.2, 10.0, 1),
               candle(10.0, 10.6, 9.3, 10.4, 2), candle(10.4, 12.5, 10.1, 12.4, 3)]
    events = [{"type": "BOS", "direction": "BULLISH", "index": 3, "origin_index": 0, "level": 10.0,
               "swing_index": 0}]
    original = config.REQUIRE_FVG_FOR_OB
    try:
        config.REQUIRE_FVG_FOR_OB = False
        free = orderblocks.find_order_blocks(candles, {"events": events}, "1h")
        assert free and free[0]["has_fvg"] is False, free
        config.REQUIRE_FVG_FOR_OB = True
        assert orderblocks.find_order_blocks(candles, {"events": events}, "1h") == []
        # FVG olan bacak zorunlulukta da korunur.
        gap = [candle(10, 10.0, 9.4, 9.5, 0), candle(9.5, 10.0, 9.2, 9.8, 1),
               candle(9.8, 12.5, 10.5, 12.4, 2), candle(12.4, 13.0, 12.0, 12.8, 3)]
        gap_events = [{"type": "BOS", "direction": "BULLISH", "index": 2, "origin_index": 0,
                       "level": 10.0, "swing_index": 0}]
        kept = orderblocks.find_order_blocks(gap, {"events": gap_events}, "1h")
        assert kept and kept[0]["has_fvg"] is True, kept
    finally:
        config.REQUIRE_FVG_FOR_OB = original
    print("REQUIRE_FVG_FOR_OB bacakta FVG zorunlu kılar: GEÇTİ")


def test_no_unused_settings():
    text = open(config.__file__, encoding="utf-8").read() if config.__file__.endswith(".py") else ""
    for name in ("TWELVEDATA_INTERVALS", "TD_RETRY_COUNT", "TD_ALWAYS_REFRESH", "BINANCE_INTERVALS",
                 "ENABLE_FVG_REQUIREMENT", "UTC_TIMEZONE"):
        assert not re.search(r"^{} =".format(name), text, re.M), name
    for name in ("CRYPTO_TOP_MIN", "REQUIRE_FVG_FOR_OB", "ENABLE_1M"):
        assert hasattr(config, name), name
    import sessions, utils
    for module, name in ((sessions, "asia_range"), (utils, "normalize_candles"),
                         (utils, "new_york_to_utc"), (phantom_scan, "_position_valid"),
                         (phantom_scan, "_levels_from_structure")):
        assert not hasattr(module, name), name
    print("Kullanılmayan ayar/fonksiyonlar kaldırıldı: GEÇTİ")


def main():
    test_top_bounds()
    test_require_fvg()
    test_no_unused_settings()
    print("test_step36: OK")


if __name__ == "__main__":
    main()
