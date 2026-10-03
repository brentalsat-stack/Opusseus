"""Adım 22: Binance evren hatası yalnız kriptoyu atlatır; forex sürer."""
import argparse

import data_binance
import phantom_scan
import synth


def main():
    synth.isolate_dirs()

    def failing(_n):
        raise data_binance.BinanceAPIError("Binance public API isteği başarısız: test")

    original = data_binance.get_top_symbols
    data_binance.get_top_symbols = failing
    try:
        errors = []
        args = argparse.Namespace(symbols=None, market="all", top=35)
        selections = phantom_scan._symbol_list(args, errors)
        assert selections and all(market == "forex" for _, market in selections), selections
        assert len(errors) == 1 and "kripto atlandı" in errors[0], errors
        crypto_only = argparse.Namespace(symbols=None, market="crypto", top=35)
        try:
            phantom_scan._symbol_list(crypto_only, [])
            raise AssertionError("yalnız kriptoda hata yükseltilmeliydi")
        except data_binance.BinanceAPIError:
            pass
    finally:
        data_binance.get_top_symbols = original
    print("Binance evren hatası forex'i durdurmuyor: GEÇTİ")
    print("test_step22: OK")


if __name__ == "__main__":
    main()
