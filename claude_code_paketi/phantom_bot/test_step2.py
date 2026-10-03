"""Adım 2 canlı Binance public API kontrolü."""
import data_binance
import synth


def main():
    synth.isolate_dirs()  # günlükler ve önbellek gerçek klasöre yazılmasın
    symbols = data_binance.get_top_symbols(35)
    print("İlk 35 USDT spot sembolü (24 saatlik quoteVolume):")
    for rank, row in enumerate(symbols, 1):
        print("{:2d}. {:12s} {:,.2f} USDT".format(rank, row["symbol"], row["quoteVolume"]))

    result = data_binance.get_klines("BTCUSDT", "1h", 3)
    print("\nBTCUSDT 1h son mumlar:")
    for candle in result["candles"][-3:]:
        print(candle)
    if result["last_candle"] is not None:
        state = "kapalı" if result["last_candle_closed"] else "AÇIK (yapı hesabına dahil değil)"
        print("Son mum durumu: {} — {}".format(state, result["last_candle"]))

    assert len(symbols) == 35, "API 35 sembolden az döndürdü"
    assert all(row["symbol"].endswith("USDT") for row in symbols)
    assert not any(row["symbol"] in ("USD1USDT", "RLUSDUSDT") for row in symbols)
    assert not any(token in row["symbol"] for row in symbols for token in ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT"))
    assert all(symbols[i]["quoteVolume"] >= symbols[i + 1]["quoteVolume"] for i in range(len(symbols) - 1))
    assert result["last_candle"] is not None
    assert result["candles"] == sorted(result["candles"], key=lambda candle: candle["t"])
    print("test_step2: OK")


if __name__ == "__main__":
    main()
