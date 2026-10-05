"""Adım 23: Twelve Data devre kesici (401/403 ve kredi limiti) kalan forex sembollerini bekletmeden atlar."""
import argparse
import time

import config
import data_twelvedata
import phantom_scan
import synth
import utils


class Env:
    def __enter__(self):
        synth.isolate_dirs()
        self.saved = (utils.http_get_json, time.sleep, config.REQUEST_DELAY_TD,
                      config.TD_CACHE_TTL_SECONDS)
        self.calls = 0
        self.sleeps = []
        time.sleep = lambda seconds: self.sleeps.append(seconds)
        config.REQUEST_DELAY_TD = 0.0
        config.TD_CACHE_TTL_SECONDS = {}
        data_twelvedata._last_request_at = None
        data_twelvedata.reset_halt()
        return self

    def respond(self, handler):
        def fake(url, timeout=None, retries=None, **kwargs):
            self.calls += 1
            return handler()
        utils.http_get_json = fake

    def __exit__(self, *exc):
        utils.http_get_json, time.sleep, config.REQUEST_DELAY_TD, config.TD_CACHE_TTL_SECONDS = self.saved
        data_twelvedata.reset_halt()


def unauthorized():
    raise RuntimeError("HTTP GET/JSON başarısız (1 deneme): HTTP Error 401: Unauthorized")


def credit_limit():
    return {"status": "error", "code": 429,
            "message": "You have run out of API credits for the day."}


def main():
    with Env() as env:
        env.respond(unauthorized)
        try:
            data_twelvedata.get_series("EUR/USD", "1h", 10)
            raise AssertionError("devre kesici açılmalıydı")
        except data_twelvedata.TwelveDataHalted:
            pass
        assert env.calls == 1 and not env.sleeps, (env.calls, env.sleeps)
        try:
            data_twelvedata.get_series("GBP/USD", "1h", 10)
            raise AssertionError("ikinci istek ağa gitmemeli")
        except data_twelvedata.TwelveDataHalted:
            pass
        assert env.calls == 1
        print("401: tek istek, beklemesiz devre kesici: GEÇTİ")

    with Env() as env:
        env.respond(credit_limit)
        try:
            data_twelvedata.get_series("EUR/USD", "1h", 10)
            raise AssertionError("kredi limitinde devre kesici açılmalıydı")
        except data_twelvedata.TwelveDataHalted:
            pass
        assert env.calls == 2, env.calls  # spec: bir kez bekleyip tekrar dene
        assert data_twelvedata.halt_reason()
        print("Kredi limiti: bir yeniden deneme, sonra devre kesici: GEÇTİ")

    with Env() as env:
        env.respond(lambda: (_ for _ in ()).throw(RuntimeError("HTTP Error 500: boom")))
        assert data_twelvedata.get_series("EUR/USD", "1h", 10) is None
        assert data_twelvedata.halt_reason() is None
        print("Geçici hata devre kesiciyi açmıyor: GEÇTİ")

    with Env() as env:
        env.respond(unauthorized)
        args = argparse.Namespace(market="forex", top=35, balance=None, risk=None,
                                  symbols="EUR/USD,GBP/USD,EUR/JPY", no_cache=False, show_all=False)
        phantom_scan.run_scan(args)
        assert env.calls == 1 and not env.sleeps, (env.calls, env.sleeps)
        print("run_scan: 3 forex sembolü için tek ağ isteği, bekleme yok: GEÇTİ")
    print("test_step23: OK")


if __name__ == "__main__":
    main()
