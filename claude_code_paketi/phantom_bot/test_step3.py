"""Adım 3 Twelve Data canlı bağlantı ve cache gözlem testi."""
import data_twelvedata
import synth


def main():
    synth.isolate_dirs()  # günlükler ve önbellek gerçek klasöre yazılmasın
    for interval in ("1h", "1day"):
        candles = data_twelvedata.get_series("EUR/USD", interval, 3)
        if candles is None:
            raise RuntimeError("EUR/USD {} verisi alınamadı; logs/run_YYYY-MM-DD.log dosyasını inceleyin".format(interval))
        print("EUR/USD {} son 3 mum (eskiden yeniye):".format(interval))
        for candle in candles[-3:]:
            print(candle)

    assert data_twelvedata.pip_size("EUR/JPY") == 0.01
    assert data_twelvedata.pip_size("XAU/USD") == 0.1
    assert data_twelvedata.pip_size("EUR/USD") == 0.0001
    print("test_step3: OK")
    print("Cache kontrolü için bu komutu ikinci kez çalıştırın; 1day cache hit logu görünmelidir.")


if __name__ == "__main__":
    main()
