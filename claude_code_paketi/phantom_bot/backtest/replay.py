"""Look-ahead'siz replay: her adımda yalnızca o ana kadar KAPANMIŞ mumlarla mevcut _scan_symbol çalışır.

Tarama mantığı değiştirilmez: yalnızca veri yükleyicisi (_load_symbol_data), saat (utils.now_utc),
günlük (utils.log_file_only) ve news dosyası yolu geçici olarak enjekte edilir.
"""
import bisect
import contextlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import fetch_history  # noqa: E402
import indicators  # noqa: E402
import liquidity  # noqa: E402
import phantom_scan  # noqa: E402
import report  # noqa: E402
import structure  # noqa: E402
import utils  # noqa: E402

# Tarama zaman dilimi adı → backtest CSV zaman dilimi
REPLAY_VERSION = 2  # önbellek şeması; değişince eski replay önbellekleri reddedilir (v2: score_breakdown eklendi)
SCAN_TIMEFRAMES = (("1day", "1d"), ("4h", "4h"), ("1h", "1h"), ("15m", "15m"), ("5m", "5m"))


class SymbolData:
    """Bir sembolün tüm zaman dilimlerindeki CSV mumları; t'ye göre kapanmış mum dilimleme."""

    def __init__(self, symbol, series, funding=None):
        self.symbol = symbol
        self.rows = {tf: list(series[tf]) for tf in fetch_history.TIMEFRAMES}
        self.times = {tf: [row[0] for row in self.rows[tf]] for tf in self.rows}
        self.funding = list(funding or [])

    @classmethod
    def load(cls, symbol, data_dir=None):
        series = {tf: fetch_history.read_klines(fetch_history.kline_path(symbol, tf, data_dir))
                  for tf in fetch_history.TIMEFRAMES}
        missing = [tf for tf, rows in series.items() if not rows]
        if missing:
            raise RuntimeError("{} için CSV verisi yok: {} (önce veriyi indirin)".format(symbol, missing))
        return cls(symbol, series, fetch_history.read_funding(fetch_history.funding_path(symbol, data_dir)))

    def closed_count(self, tf, t):
        """t anında kapanmış mum sayısı (açılış + süre <= t)."""
        return bisect.bisect_right(self.times[tf], t - fetch_history.INTERVAL_SECONDS[tf])

    def closed(self, tf, t, limit=None):
        end = self.closed_count(tf, t)
        start = max(0, end - (limit or config.BINANCE_KLINE_LIMIT))
        return [{"t": r[0], "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]}
                for r in self.rows[tf][start:end]]

    def series_at(self, t):
        """_scan_symbol'ün beklediği sözlük: yalnızca kapanmış mumlar + güncel fiyat için '1h_last'."""
        series = {}
        for scan_tf, csv_tf in SCAN_TIMEFRAMES:
            candles = self.closed(csv_tf, t)
            if not candles:
                raise RuntimeError("{} {} için t={} anında kapanmış mum yok".format(self.symbol, csv_tf, t))
            series[scan_tf] = candles
            series[scan_tf + "_last"] = candles[-1]
        last_5m = series["5m"][-1]
        # Güncel fiyat = son kapanmış 5m kapanışı; açık 1h mumu yerine geçen yapay mum (yalnızca t ve c okunur).
        hour_open = (int(t) // 3600) * 3600
        series["1h_last"] = {"t": hour_open, "o": last_5m["c"], "h": last_5m["c"],
                             "l": last_5m["c"], "c": last_5m["c"], "v": 0.0}
        return series


@contextlib.contextmanager
def replay_environment(t, data):
    """Taramayı t anına sabitler: veri yükleyici, saat, günlük ve news dosyası geçici olarak değişir."""
    series = data.series_at(t)
    saved = (phantom_scan._load_symbol_data, utils.now_utc, utils.log_file_only, config.NEWS_CSV)
    phantom_scan._load_symbol_data = lambda *args, **kwargs: series
    utils.now_utc = lambda: datetime.fromtimestamp(t, timezone.utc)
    utils.log_file_only = lambda message: None
    config.NEWS_CSV = os.path.join(config.BT_BASE_DIR, "__news_yok__.csv")  # geçmiş için haber verisi yok
    try:
        yield series
    finally:
        phantom_scan._load_symbol_data, utils.now_utc, utils.log_file_only, config.NEWS_CSV = saved


def setup_key(candidate):
    """Aynı POI = sembol + yön + POI TF + proximal + distal."""
    return (candidate["symbol"], candidate["direction"], candidate["poi_tf"],
            round(float(candidate["poi_proximal"]), 12), round(float(candidate["poi_distal"]), 12))


def _record(candidate, t, series):
    """Aday sözlüğünden JSON'a yazılabilir setup kaydı; confirmation simülasyonu için bağlam ekler."""
    h4 = series["4h"][-phantom_scan.ANALYSIS_CANDLES:]
    structure_h4 = structure.analyze_structure(h4)
    reference = series["1h_last"]["t"]
    pd = liquidity.pdh_pdl(series["1h"], reference)
    pw = liquidity.pwh_pwl(series["1h"], reference)
    market = candidate.get("market", "crypto")
    distance = report._distance_pct(candidate)
    keep = ("symbol", "direction", "poi_tf", "poi_proximal", "poi_distal", "poi_eq", "poi_state", "poi_stack",
            "status", "entry_type", "entry", "stop", "stop_pips_or_pct", "tp1", "tp2", "rr_tp1", "rr_tp2",
            "score", "grade", "premium_discount", "warnings", "last_price", "ltf_tf", "ltf_ob", "bos_time",
            "stack_count", "htf_bias_d1", "htf_bias_h4", "targeted", "protected", "range_low", "range_high",
            "score_breakdown")
    record = {key: candidate.get(key) for key in keep}
    record.update({
        "key": list(setup_key(candidate)),
        "market": market,
        "first_seen_t": int(t),
        "distance_pct": distance,
        "actionable": report._is_actionable(dict(candidate, distance_pct=distance, market=market)),
        "ctx": {"irl": phantom_scan._irl_levels(h4, structure_h4),
                "targeted": candidate.get("targeted"),
                "pd": pd, "pw": pw},
        "risk": None,
    })
    if candidate.get("entry_type") == "risk":
        record["risk"] = {"t": int(t), "entry": candidate["entry"], "stop": candidate["stop"],
                          "tp1": candidate["tp1"], "tp2": candidate["tp2"],
                          "stop_pips_or_pct": candidate["stop_pips_or_pct"], "warnings": candidate["warnings"]}
    return record


def replay_symbol(symbol, data, t_start, t_end, step_s, scan=None, progress=None):
    """[t_start, t_end] aralığında step_s adımlarla taramayı çalıştırır; tekilleştirilmiş setup kayıtlarını döndürür.

    Aynı POI tekrar çıkarsa ilk görüldüğü andaki seviyeler korunur; yalnızca ilk 'risk' girişli aday
    ``risk`` alanına yazılır (sonradan ENTRY_READY olan POI'lerde risk seviyesi o ana kadar kaydedilmiştir).
    """
    scan = scan or phantom_scan._scan_symbol
    setups = {}
    t = int(t_start)
    count = 0
    while t <= t_end:
        count += 1
        with replay_environment(t, data) as series:
            try:
                candidates, _ = scan(symbol, "crypto", False, lambda *a: None)
            except Exception as exc:  # tek adım hatası taramayı durdurmaz
                candidates = []
                if progress:
                    progress("{} t={} tarama hatası: {}".format(symbol, t, utils.mask_secrets(exc)))
            for candidate in candidates:
                candidate = dict(candidate, market="crypto")
                key = setup_key(candidate)
                existing = setups.get(key)
                if existing is None:
                    setups[key] = _record(candidate, t, series)
                elif existing["risk"] is None and candidate.get("entry_type") == "risk":
                    existing["risk"] = {"t": int(t), "entry": candidate["entry"], "stop": candidate["stop"],
                                        "tp1": candidate["tp1"], "tp2": candidate["tp2"],
                                        "stop_pips_or_pct": candidate["stop_pips_or_pct"],
                                        "warnings": candidate["warnings"]}
        if progress and count % 50 == 0:
            progress("{} replay {} adım".format(symbol, count))
        t += step_s
    return sorted(setups.values(), key=lambda r: (r["first_seen_t"], r["key"]))


# ---------------------------------------------------------------- çok süreçli çalıştırma
def replay_worker(job):
    """Modül düzeyinde tanımlı işçi (Windows spawn için pickle edilebilir). job: sözlük."""
    data = SymbolData.load(job["symbol"], job["data_dir"])
    records = replay_symbol(job["symbol"], data, job["t_start"], job["t_end"], job["step_s"])
    return job["symbol"], records


def replay_range(data_dir, days, step_hours, symbol=None):
    """CSV verisine göre replay penceresi: son kapanmış 5m'ye kadar `days` gün."""
    sample = fetch_history.read_klines(fetch_history.kline_path(symbol or config.BACKTEST_SYMBOLS[0], "5m", data_dir))
    if not sample:
        raise RuntimeError("5m CSV verisi yok")
    t_end = sample[-1][0] + 300
    step_s = int(step_hours * 3600)
    t_start = ((t_end - days * 86400) // step_s) * step_s
    return t_start, t_end, step_s


def cache_path(symbol, results_dir=None):
    return os.path.join(results_dir or config.BT_RESULTS_DIR, "replay", "replay_{}.json".format(symbol))


def replay_all(symbols, data_dir, days, step_hours, workers=1, results_dir=None, force=False,
               print_fn=print, t_window=None):
    """Tüm semboller için replay; sonuçlar sembol listesi sırasına göre (deterministik) birleştirilir.

    Sembol başına sonuç JSON önbelleğe yazılır; aynı pencere için tekrar çalıştırmada yeniden kullanılır.
    """
    t_start, t_end, step_s = t_window or replay_range(data_dir, days, step_hours, symbols[0])
    window = {"t_start": t_start, "t_end": t_end, "step_s": step_s, "version": REPLAY_VERSION}
    results, jobs = {}, []
    for symbol in symbols:
        path = cache_path(symbol, results_dir)
        cached = None
        if not force and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                cached = json.load(handle)
        if cached and cached.get("window") == window:
            results[symbol] = cached["setups"]
            print_fn("replay {} önbellekten ({} setup)".format(symbol, len(cached["setups"])))
        else:
            jobs.append({"symbol": symbol, "data_dir": data_dir, **window})
    if jobs:
        print_fn("replay: {} sembol, {} adım/sembol, {} işçi".format(
            len(jobs), (t_end - t_start) // step_s + 1, workers))
        if workers > 1 and len(jobs) > 1:
            import multiprocessing
            context = multiprocessing.get_context("spawn")
            with context.Pool(processes=min(workers, len(jobs))) as pool:
                for symbol, records in pool.imap(replay_worker, jobs):  # imap sıralıdır
                    results[symbol] = records
                    print_fn("replay {} bitti ({} setup)".format(symbol, len(records)))
        else:
            for job in jobs:
                symbol, records = replay_worker(job)
                results[symbol] = records
                print_fn("replay {} bitti ({} setup)".format(symbol, len(records)))
        for job in jobs:
            path = cache_path(job["symbol"], results_dir)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"window": window, "setups": results[job["symbol"]]}, handle,
                          ensure_ascii=False, default=str)
    merged = []
    for symbol in symbols:
        merged.extend(results.get(symbol, []))
    merged.sort(key=lambda r: (r["first_seen_t"], r["symbol"], r["key"]))
    return merged, window
