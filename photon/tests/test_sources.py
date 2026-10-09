import json
import lzma
import struct
from datetime import datetime, timedelta
from decimal import Decimal as D

import pytest

from photon.data import CandleStore, Timeframe
from photon.data.sources import dukascopy, oanda
from photon.data.sources.http import RateLimited, get_with_retry
from photon.data.sources.ibkr import to_tick
from photon.tests.helpers import UTC

PIP = D("0.0001")
H = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)


def bi5(records):
    raw = b"".join(struct.pack(">IIIff", ms, ask, bid, 1.0, 1.0) for ms, ask, bid in records)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def test_url_month_is_zero_based():
    u = dukascopy.hour_url("https://x/datafeed/", "EURUSD", H)
    assert u == "https://x/datafeed/EURUSD/2021/08/01/08h_ticks.bi5"


def test_decode_ticks():
    data = bi5([(0, 118_005, 118_000), (30_000, 118_010, 118_004)])
    t = dukascopy.decode_ticks(data, "EURUSD", H, PIP)
    assert t[0].bid == D("1.18000") and t[0].ask == D("1.18005") and t[0].time == H
    assert t[1].time == H + timedelta(seconds=30)
    assert dukascopy.decode_ticks(b"", "EURUSD", H, PIP) == []
    with pytest.raises(ValueError):
        dukascopy.decode_ticks(lzma.compress(b"x" * 21, format=lzma.FORMAT_ALONE), "EURUSD", H, PIP)


def test_jpy_scale():
    t = dukascopy.decode_ticks(bi5([(0, 110_005, 110_000)]), "USDJPY", H, D("0.01"))
    assert t[0].bid == D("110.000")


def make_client(tmp_path, responses, calls):
    def get(url, headers):
        calls.append(url)
        return responses.pop(0)
    return dukascopy.DukascopyClient("https://x/d", tmp_path, 0, 3, http_get=get, sleep=lambda s: None)


def test_download_m1_caches_raw_and_resumes(tmp_path):
    calls = []
    data = bi5([(0, 118_005, 118_000), (61_000, 118_010, 118_004)])
    c = make_client(tmp_path, [(200, data, {}), (404, b"", {})], calls)
    store = CandleStore(":memory:")
    n = c.download_m1("EURUSD", "EURUSD", PIP, H, H + timedelta(hours=2), store)
    assert n == 2 and len(calls) == 2
    assert store.chunk_status("DUKASCOPY", "EURUSD", "2021090108") == "OK"
    assert store.chunk_status("DUKASCOPY", "EURUSD", "2021090109") == "EMPTY"
    # ikinci çalıştırma: ağ isteği yok
    assert c.download_m1("EURUSD", "EURUSD", PIP, H, H + timedelta(hours=2), store) == 0 and len(calls) == 2
    # chunk kaydı silinse bile ham dosya diskten gelir
    c2 = make_client(tmp_path, [], calls)
    assert c2.download_m1("EURUSD", "EURUSD", PIP, H, H + timedelta(hours=1), CandleStore(":memory:")) == 2


def test_retry_on_429_then_success_and_exhaustion():
    sleeps, seq = [], [(429, b"", {"Retry-After": "7"}), (200, b"ok", {})]
    st, body = get_with_retry("u", {}, lambda u, h: seq.pop(0), 3, sleeps.append)
    assert (st, body) == (200, b"ok") and sleeps == [7.0]
    with pytest.raises(RateLimited):
        get_with_retry("u", {}, lambda u, h: (429, b"", {}), 2, lambda s: None)
    with pytest.raises(RuntimeError):
        get_with_retry("u", {}, lambda u, h: (403, b"no", {}), 2, lambda s: None)


def oanda_payload(times, complete=True):
    return json.dumps({"candles": [
        {"time": t.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"), "complete": complete, "volume": 5,
         "bid": {"o": "1.18000", "h": "1.18010", "l": "1.17990", "c": "1.18005"},
         "ask": {"o": "1.18010", "h": "1.18020", "l": "1.18000", "c": "1.18015"}} for t in times]}).encode()


def test_oanda_parse_and_filters(monkeypatch):
    monkeypatch.setenv("TOK", "secret")
    calls = []

    def get(url, headers):
        calls.append((url, headers))
        return 200, oanda_payload([H, H + timedelta(minutes=1)]) + b"", {}

    # son mum complete=false → atlanır
    payload = json.loads(oanda_payload([H, H + timedelta(minutes=1)]))
    payload["candles"][1]["complete"] = False
    c = oanda.OandaClient("h", "TOK", http_get=lambda u, h: (calls.append((u, h)) or (200, json.dumps(payload).encode(), {})))
    out = c.fetch_m1("EURUSD", "EUR_USD", H, H + timedelta(hours=1))
    assert len(out) == 1 and out[0].bid.close == D("1.18005") and out[0].ask.open == D("1.18010")
    assert out[0].tf is Timeframe.M1 and out[0].open_time == H
    url, hdr = calls[0]
    assert "price=BA" in url and "granularity=M1" in url and hdr["Authorization"] == "Bearer secret"


def test_oanda_requires_token(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    with pytest.raises(RuntimeError, match="NOPE"):
        oanda.OandaClient("h", "NOPE")


def test_ibkr_to_tick():
    t = to_tick("EURUSD", 1.18, 1.18005, H, PIP)
    assert t.bid == D("1.18000") and t.ask == D("1.18005")
    assert to_tick("EURUSD", float("nan"), 1.1, H, PIP) is None
    assert to_tick("EURUSD", -1.0, 1.1, H, PIP) is None
