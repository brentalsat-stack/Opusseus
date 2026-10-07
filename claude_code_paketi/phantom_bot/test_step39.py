"""Adım 39: --source / CRYPTO_DATA_SOURCE seçimi; rapor ve log'da kaynak etiketi."""
import argparse
import contextlib
import glob
import io
import json
import os

import config
import data_binance
import data_futures
import phantom_scan
import synth

INTERVALS = {"1d": "1day", "4h": "4h", "1h": "1h", "15m": "15m", "5m": "5m"}


def run(source, market="crypto"):
    root = synth.isolate_dirs()
    calls = {"spot": 0, "futures": 0}
    data = synth.make_data(3)

    def make(name):
        def get_klines(symbol, interval, limit):
            calls[name] += 1
            tf = INTERVALS[interval]
            return {"candles": data[tf], "last_candle": data[tf][-1], "last_candle_closed": True}
        return get_klines

    saved = (data_binance.get_klines, data_futures.get_klines, config.CRYPTO_DATA_SOURCE)
    data_binance.get_klines, data_futures.get_klines = make("spot"), make("futures")
    try:
        args = phantom_scan.parse_args(["--market", market, "--symbols", "AAAUSDT"] +
                                       (["--source", source] if source else []))
        with contextlib.redirect_stdout(io.StringIO()):
            paths = phantom_scan.run_scan(args)
    finally:
        data_binance.get_klines, data_futures.get_klines, config.CRYPTO_DATA_SOURCE = saved
    markdown = open(paths["md"], encoding="utf-8").read()
    meta = json.load(open(paths["json"], encoding="utf-8"))["meta"]
    log = open(glob.glob(os.path.join(root, "logs", "run_*.log"))[0], encoding="utf-8").read()
    return calls, markdown, meta, log


def main():
    assert config.CRYPTO_DATA_SOURCE == "spot"
    assert phantom_scan.parse_args(["--source", "futures"]).source == "futures"
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            phantom_scan.parse_args(["--source", "perp"])
        raise AssertionError("geçersiz --source reddedilmeliydi")
    except SystemExit:
        pass

    calls, markdown, meta, log = run("futures")
    assert calls["futures"] == 5 and calls["spot"] == 0, calls
    assert "Kripto veri kaynağı: Binance USDⓈ-M perpetual (futures)" in markdown
    assert meta["crypto_source"].endswith("(futures)") and "Kripto veri kaynağı: Binance USDⓈ-M" in log

    calls, markdown, meta, log = run(None)  # config varsayılanı: spot
    assert calls["spot"] == 5 and calls["futures"] == 0, calls
    assert "Kripto veri kaynağı: Binance spot" in markdown and "Kripto veri kaynağı: Binance spot" in log

    config.CRYPTO_DATA_SOURCE = "bozuk"
    try:
        phantom_scan.crypto_source()
        raise AssertionError("bozuk config reddedilmeliydi")
    except ValueError:
        pass
    finally:
        config.CRYPTO_DATA_SOURCE = "spot"
    print("--source/CRYPTO_DATA_SOURCE seçimi ve kaynak etiketi: GEÇTİ")
    print("test_step39: OK")


if __name__ == "__main__":
    main()
