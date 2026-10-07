"""Binance USDⓈ-M perpetual geçmiş veri indirici (kline + funding) ve CSV önbelleği.

Yalnızca public (anahtarsız) uç noktalar. Tekrar çalıştırmada yalnızca eksik kısım indirilir.
Windows ve a-Shell'de çalışır (yollar os.path ile).
"""
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import data_binance  # noqa: E402
import data_futures  # noqa: E402
import utils  # noqa: E402

TIMEFRAMES = ("1d", "4h", "1h", "15m", "5m")
INTERVAL_SECONDS = {"1d": 86400, "4h": 14400, "1h": 3600, "15m": 900, "5m": 300}
KLINE_HEADER = ["t", "o", "h", "l", "c", "v"]
FUNDING_HEADER = ["t", "rate"]
FUNDING_PAGE = 1000


# ---------------------------------------------------------------- yollar / CSV
def kline_path(symbol, timeframe, data_dir=None):
    return os.path.join(data_dir or config.BT_DATA_DIR, "klines_{}_{}.csv".format(symbol, timeframe))


def funding_path(symbol, data_dir=None):
    return os.path.join(data_dir or config.BT_DATA_DIR, "funding_{}.csv".format(symbol))


def read_klines(path):
    """CSV'yi [(t, o, h, l, c, v), ...] (eskiden yeniye) olarak okur; dosya yoksa []."""
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) >= 6:
                rows.append((int(row[0]), float(row[1]), float(row[2]), float(row[3]),
                             float(row[4]), float(row[5])))
    return rows


def read_funding(path):
    """CSV'yi [(t_epoch_s, rate), ...] olarak okur; dosya yoksa []."""
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                rows.append((int(row[0]), float(row[1])))
    return rows


def _write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    os.replace(temporary, path)


def merge_rows(old, new):
    """t'ye göre tekilleştirir (yeni kayıt eskisini ezer) ve sıralar."""
    merged = {row[0]: row for row in old}
    merged.update({row[0]: row for row in new})
    return [merged[key] for key in sorted(merged)]


def count_gaps(rows, timeframe):
    """Ardışık mumlar arasındaki eksik mum sayısı (bilgi amaçlı)."""
    step = INTERVAL_SECONDS[timeframe]
    return sum(max(0, (rows[i][0] - rows[i - 1][0]) // step - 1) for i in range(1, len(rows)))


# ---------------------------------------------------------------- şema günlüğü
def schema_of(payload):
    """Yanıtın ALAN ADLARINI (değer değil) kısa bir metne çevirir; ilk Windows koşusunda şema doğrulaması için."""
    if isinstance(payload, dict):
        parts = ["dict keys=" + ",".join(sorted(payload))]
        for key, value in sorted(payload.items()):
            if isinstance(value, list) and value and isinstance(value[0], dict):
                parts.append("{}[0] keys={}".format(key, ",".join(sorted(value[0]))))
        return "; ".join(parts)
    if isinstance(payload, list):
        if not payload:
            return "list (boş)"
        first = payload[0]
        if isinstance(first, dict):
            return "list of dict keys=" + ",".join(sorted(first))
        if isinstance(first, (list, tuple)):
            return "list of list, sütun sayısı={}".format(len(first))
        return "list of {}".format(type(first).__name__)
    return type(payload).__name__


class SchemaLog:
    """İlk ``limit`` ham yanıtın şemasını kaydeder (uç nokta başına bir kez)."""

    def __init__(self, limit=2):
        self.limit = limit
        self.lines = []
        self.seen = set()

    def record(self, label, payload):
        if len(self.lines) >= self.limit or label in self.seen:
            return
        self.seen.add(label)
        line = "ŞEMA {}: {}".format(label, schema_of(payload))
        self.lines.append(line)
        print(line)
        utils.log_file_only(line)


# ---------------------------------------------------------------- HTTP
class Throttle:
    """İstekler arası bekleme + dakikalık ağırlık sınırı (X-MBX-USED-WEIGHT-1M)."""

    def __init__(self):
        self.last = 0.0

    def wait(self, headers=None):
        used = None
        if headers:
            try:
                used = int(headers.get("x-mbx-used-weight-1m"))
            except (TypeError, ValueError):
                used = None
        if used is not None and used >= config.BT_WEIGHT_LIMIT_SOFT:
            pause = 61 - (time.time() % 60)
            print("  fapi ağırlığı {} — {:.0f} sn bekleniyor".format(used, pause))
            time.sleep(pause)
        remaining = config.BT_REQUEST_DELAY - (time.monotonic() - self.last)
        if remaining > 0:
            time.sleep(remaining)
        self.last = time.monotonic()


def default_request(path, params):
    return data_futures.request_json(path, params, with_headers=True)


# ---------------------------------------------------------------- kline indirme
def fetch_klines_range(symbol, timeframe, start_s, end_s, request=default_request, throttle=None,
                       schema=None, now_ms=None, progress=None):
    """[start_s, end_s) aralığındaki KAPANMIŞ mumları 1500'lük sayfalarla indirir.

    Dönüş: [(t, o, h, l, c, v), ...] eskiden yeniye.
    """
    throttle = throttle or Throttle()
    step_ms = INTERVAL_SECONDS[timeframe] * 1000
    cursor_ms, end_ms = int(start_s) * 1000, int(end_s) * 1000
    rows, page_no, headers = [], 0, None
    while cursor_ms < end_ms:
        throttle.wait(headers)
        payload, headers = request(config.BINANCE_FUTURES_KLINES_PATH, {
            "symbol": symbol, "interval": timeframe, "startTime": cursor_ms,
            "endTime": end_ms - 1, "limit": config.BINANCE_FUTURES_KLINE_PAGE})
        if schema is not None:
            schema.record("klines", payload)
        if not isinstance(payload, list):
            raise data_futures.FuturesAPIError("Kline yanıtı liste biçiminde değil: {}".format(schema_of(payload)))
        page_no += 1
        if progress:
            progress(page_no)
        if not payload:
            break
        parsed = data_binance.parse_klines(payload, now_ms=now_ms)["candles"]
        rows.extend((c["t"], c["o"], c["h"], c["l"], c["c"], c["v"]) for c in parsed)
        last_open_ms = int(payload[-1][0])
        if len(payload) < config.BINANCE_FUTURES_KLINE_PAGE:
            break
        cursor_ms = last_open_ms + step_ms
    return rows


def update_klines(symbol, timeframe, need_start_s, end_s, data_dir=None, **kwargs):
    """CSV önbelleğini [need_start_s, end_s) için tamamlar; yalnızca eksik kısmı indirir."""
    path = kline_path(symbol, timeframe, data_dir)
    step = INTERVAL_SECONDS[timeframe]
    need_start_s = (int(need_start_s) // step) * step
    end_s = (int(end_s) // step) * step
    rows = read_klines(path)
    fetched = 0
    if rows and rows[0][0] <= need_start_s:
        if rows[-1][0] + step < end_s:
            new = fetch_klines_range(symbol, timeframe, rows[-1][0] + step, end_s, **kwargs)
            fetched += len(new)
            rows = merge_rows(rows, new)
    else:
        upper = rows[0][0] if rows else end_s
        new = fetch_klines_range(symbol, timeframe, need_start_s, upper, **kwargs)
        fetched += len(new)
        rows = merge_rows(rows, new)
        if rows and rows[-1][0] + step < end_s:
            tail = fetch_klines_range(symbol, timeframe, rows[-1][0] + step, end_s, **kwargs)
            fetched += len(tail)
            rows = merge_rows(rows, tail)
    if fetched:
        _write_csv(path, KLINE_HEADER, rows)
    return rows, fetched


# ---------------------------------------------------------------- funding
def parse_funding(payload):
    """fundingRate yanıtı → [(t_epoch_s, rate), ...]. Şema: [{symbol, fundingTime(ms), fundingRate(str), ...}]."""
    if not isinstance(payload, list):
        raise data_futures.FuturesAPIError("fundingRate yanıtı liste biçiminde değil: {}".format(schema_of(payload)))
    rows = []
    for item in payload:
        if isinstance(item, dict) and "fundingTime" in item and "fundingRate" in item:
            rows.append((int(item["fundingTime"]) // 1000, float(item["fundingRate"])))
    return rows


def fetch_funding_range(symbol, start_s, end_s, request=default_request, throttle=None, schema=None):
    throttle = throttle or Throttle()
    cursor_ms, end_ms = int(start_s) * 1000, int(end_s) * 1000
    rows, headers = [], None
    while cursor_ms < end_ms:
        throttle.wait(headers)
        payload, headers = request(config.BINANCE_FUTURES_FUNDING_PATH, {
            "symbol": symbol, "startTime": cursor_ms, "endTime": end_ms, "limit": FUNDING_PAGE})
        if schema is not None:
            schema.record("fundingRate", payload)
        page = parse_funding(payload)
        rows.extend(page)
        if len(payload) < FUNDING_PAGE or not page:
            break
        cursor_ms = page[-1][0] * 1000 + 1
    return rows


def update_funding(symbol, start_s, end_s, data_dir=None, **kwargs):
    path = funding_path(symbol, data_dir)
    rows = read_funding(path)
    if rows and rows[0][0] <= start_s + 8 * 3600:
        new = fetch_funding_range(symbol, rows[-1][0] + 1, end_s, **kwargs) if rows[-1][0] + 8 * 3600 < end_s else []
    else:
        new = fetch_funding_range(symbol, start_s, end_s, **kwargs)
    fetched = len(new)
    if fetched:
        rows = merge_rows(rows, new)
        _write_csv(path, FUNDING_HEADER, rows)
    return rows, fetched


# ---------------------------------------------------------------- toplu
def required_start_s(timeframe, end_s, days):
    """Replay başlangıcı (end - days) ve ısınma verisine göre bir TF için gereken ilk zaman."""
    return int(end_s) - (int(days) + int(config.BT_WARMUP_DAYS[timeframe])) * 86400


def fetch_all(symbols, days, end_s=None, data_dir=None, request=default_request, schema=None,
              now_ms=None, print_fn=print):
    """Tüm sembol/TF için klines + funding önbelleğini tamamlar. Dönüş: {sembol: {tf: satır sayısı}}."""
    if end_s is None:
        end_s = (int(time.time()) // 300) * 300  # son tam 5m sınırı
    throttle = Throttle()
    summary = {}
    total = len(symbols)
    for index, symbol in enumerate(symbols, 1):
        summary[symbol] = {}
        for timeframe in TIMEFRAMES:
            def progress(page, _s=symbol, _t=timeframe, _i=index):
                print_fn("[{}/{}] {} {} sayfa {}".format(_i, total, _s, _t, page))
            rows, fetched = update_klines(
                symbol, timeframe, required_start_s(timeframe, end_s, days), end_s, data_dir=data_dir,
                request=request, throttle=throttle, schema=schema, now_ms=now_ms, progress=progress)
            summary[symbol][timeframe] = len(rows)
            wanted = required_start_s(timeframe, end_s, days)
            if rows and rows[0][0] > wanted + 2 * INTERVAL_SECONDS[timeframe]:
                print_fn("[{}/{}] UYARI: {} {} geçmişi istenenden kısa (ilk mum {} gün geç); bu sembol için daha kısa bir pencere kullanılacak".format(
                    index, total, symbol, timeframe, (rows[0][0] - wanted) // 86400))
            gaps = count_gaps(rows, timeframe)
            print_fn("[{}/{}] {} {} OK ({} mum, +{} yeni{})".format(
                index, total, symbol, timeframe, len(rows), fetched,
                ", {} eksik mum".format(gaps) if gaps else ""))
        funding, fetched = update_funding(symbol, end_s - (days + 1) * 86400, end_s, data_dir=data_dir,
                                          request=request, throttle=throttle, schema=schema)
        summary[symbol]["funding"] = len(funding)
        print_fn("[{}/{}] {} funding OK ({} kayıt, +{} yeni)".format(index, total, symbol, len(funding), fetched))
    return summary
