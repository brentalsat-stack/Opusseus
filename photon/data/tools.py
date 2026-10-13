"""İndirme/dışa aktarma/denetim yardımcıları (CLI tarafından kullanılır)."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from .cache import CandleStore
from .models import QuoteCandle, Timeframe
from .sources import dukascopy, histdata, oanda
from .tz import UTC

SOURCES = (histdata.SOURCE, oanda.SOURCE, dukascopy.SOURCE)


def day_range(start: date, end_inclusive: date) -> tuple[datetime, datetime]:
    return (datetime(start.year, start.month, start.day, tzinfo=UTC),
            datetime(end_inclusive.year, end_inclusive.month, end_inclusive.day, tzinfo=UTC) + timedelta(days=1))


def open_store(cfg) -> CandleStore:
    cfg.require("data_cache")
    return CandleStore(cfg.get("data.backtest.cache.db"))


def fetch(cfg, source: str, pair: str, start: datetime, end: datetime) -> int:
    """Seçilen kaynaktan M1 bid/ask indirip önbelleğe yazar (devam edilebilir)."""
    store = open_store(cfg)
    try:
        if source == dukascopy.SOURCE:
            cfg.require("hist_dukascopy")
            d = cfg.get("data.backtest.dukascopy")
            client = dukascopy.DukascopyClient(d["base_url"], cfg.get("data.backtest.cache.raw_dir"),
                                               float(d["request_delay_s"]), d["max_retries"])
            return client.download_m1(pair, cfg.get(f"pair_params.{pair}.symbols.dukascopy"),
                                      cfg.pip_size(pair), start, end, store)
        if source == oanda.SOURCE:
            cfg.require("hist_oanda")
            o = cfg.get("data.backtest.oanda")
            client = oanda.OandaClient(o["rest_host"], o["token_env"])
            return client.download_m1(pair, cfg.get(f"pair_params.{pair}.symbols.oanda"), start, end, store)
        if source == histdata.SOURCE:
            raise ValueError("HISTDATA dosya kaynaklıdır: `python -m photon import-histdata` kullanın")
        raise ValueError(f"bilinmeyen kaynak {source!r}; geçerli: {', '.join(SOURCES)}")
    finally:
        store.close()


def load_m1(cfg, source: str, pair: str, start: datetime, end: datetime) -> list[QuoteCandle]:
    store = open_store(cfg)
    try:
        return list(store.get_candles(source, pair, Timeframe.M1, start, end))
    finally:
        store.close()


_HEADER = ["time_utc", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "n_ticks"]


def data_bounds(cfg, source: str, pair: str) -> tuple[datetime, datetime] | None:
    """Önbellekteki M1 verisinin [ilk, son] mum zamanı (UTC) — başlangıç/warm-up kontrolleri bununla yapılır (boş aralık sorgusuyla değil)."""
    store = open_store(cfg)
    try:
        return store.bounds(source, pair, Timeframe.M1)
    finally:
        store.close()


def export_csv(candles: Iterable[QuoteCandle], path: str | Path) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_HEADER)
        for c in candles:
            w.writerow([c.open_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        *(str(x) for x in (c.bid.open, c.bid.high, c.bid.low, c.bid.close,
                                           c.ask.open, c.ask.high, c.ask.low, c.ask.close)), c.n_ticks])
            n += 1
    return n


def import_histdata(cfg, pair: str, path: str | None = None, years: tuple[int, int] | None = None) -> "histdata.MultiReport":
    """HistData M1 (bid) dosya(lar)ını önbelleğe alır; ask = bid + costs.spread_pips. `path`: dosya, dizin (DAT_ASCII_<PAIR>_M1_<YYYY>.csv'ler)
    veya glob; verilmezse config data.backtest.histdata.path (o da dosya/dizin/glob olabilir). Yıllar tek önbellekte birleştirilir."""
    cfg.require("hist_histdata")
    paths = histdata.resolve_paths(path or cfg.get("data.backtest.histdata.path"), pair, years)
    if not paths:
        raise FileNotFoundError(f"HistData dosyası bulunamadı: {path or cfg.get('data.backtest.histdata.path')}")
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"HistData dosyası yok: {missing[0]}")
    store = open_store(cfg)
    try:
        return histdata.import_many(paths, pair, cfg.pip_size(pair), Decimal(str(cfg.get("costs.spread_pips"))),
                                    cfg.get("data.backtest.histdata.utc_offset_hours"), store)
    finally:
        store.close()
