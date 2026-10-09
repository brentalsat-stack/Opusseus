"""Ortak HTTP yardımcıları (stdlib). Ortam proxy/CA ayarlarını (HTTPS_PROXY, SSL_CERT_FILE) kullanır."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Callable, Mapping

HttpGet = Callable[[str, Mapping[str, str]], tuple[int, bytes, Mapping[str, str]]]


class RateLimited(RuntimeError):
    pass


def default_get(url: str, headers: Mapping[str, str]) -> tuple[int, bytes, Mapping[str, str]]:
    req = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})


def get_with_retry(url: str, headers: Mapping[str, str], http_get: HttpGet, max_retries: int,
                   sleep: Callable[[float], None] = time.sleep) -> tuple[int, bytes]:
    """429/5xx için üstel bekleme (Retry-After'a saygılı). Tükenirse RateLimited / RuntimeError."""
    for attempt in range(max_retries + 1):
        try:
            status, body, hdr = http_get(url, headers)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:  # bağlantı kopması = geçici
            if attempt == max_retries:
                raise RuntimeError(f"{url}: ağ hatası, {max_retries} denemeden sonra vazgeçildi: {e}") from e
            sleep(min(2 ** attempt * 5, 120))
            continue
        if status < 400 or status == 404:
            return status, body
        if attempt == max_retries:
            break
        if status == 429 or status >= 500:
            ra = {k.lower(): v for k, v in hdr.items()}.get("retry-after")
            sleep(float(ra) if ra and ra.replace(".", "", 1).isdigit() else min(2 ** attempt * 5, 120))
        else:
            break
    if status == 429:
        raise RateLimited(f"{url}: 429 Too Many Requests, {max_retries} denemeden sonra vazgeçildi")
    raise RuntimeError(f"{url}: HTTP {status}: {body[:200]!r}")
