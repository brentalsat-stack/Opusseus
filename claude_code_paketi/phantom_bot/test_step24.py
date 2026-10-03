"""Adım 24: hata mesajları ve traceback API anahtarını sızdırmaz; traceback yalnız log dosyasına gider."""
import argparse
import contextlib
import glob
import io
import json
import os

import config
import phantom_scan
import synth

SECRET = "SUPERGIZLIANAHTAR123"


def main():
    root = synth.isolate_dirs()
    config.TWELVEDATA_API_KEY = SECRET
    original = phantom_scan._scan_symbol

    def boom(symbol, market, no_cache, progress):
        raise RuntimeError("istek başarısız: https://api.twelvedata.com/time_series?symbol=X&apikey={}".format(SECRET))

    phantom_scan._scan_symbol = boom
    buffer = io.StringIO()
    try:
        args = argparse.Namespace(market="forex", top=35, balance=None, risk=None,
                                  symbols="EUR/USD", no_cache=False, show_all=False)
        with contextlib.redirect_stdout(buffer):
            phantom_scan.run_scan(args)
    finally:
        phantom_scan._scan_symbol = original
        config.TWELVEDATA_API_KEY = "BURAYA_ANAHTAR"

    blob = buffer.getvalue()
    for path in glob.glob(os.path.join(root, "*", "*")):
        with open(path, encoding="utf-8-sig") as handle:
            blob += handle.read()
    assert SECRET not in blob, "API anahtarı çıktıya sızdı"
    assert "apikey=***" in blob
    printed_traceback = [line for line in buffer.getvalue().splitlines() if "traceback" in line.lower()]
    assert not printed_traceback, printed_traceback
    log_text = open(glob.glob(os.path.join(root, "logs", "run_*.log"))[0], encoding="utf-8").read()
    assert "traceback (son 3 satır)" in log_text
    meta = json.load(open(glob.glob(os.path.join(root, "scans", "scan_*.json"))[0], encoding="utf-8"))["meta"]
    assert meta["errors"] and SECRET not in json.dumps(meta)
    print("Hata/traceback maskeli, traceback ekrana yazılmıyor: GEÇTİ")
    print("test_step24: OK")


if __name__ == "__main__":
    main()
