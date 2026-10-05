"""Adım 33: ACTIONABLE_DISTANCE_PCT; uzak POI'ler yalnız 'Uzak POI'ler' bölümünde, actionable alanı CSV/JSON'da."""
import csv
import json
from datetime import datetime, timezone

import config
import report
import synth


def row(symbol, market, entry, last, score=80, rr=6.0, rank=1, **extra):
    item = {"market": market, "symbol": symbol, "direction": "BULLISH", "score": score,
            "status": "WAITING_TAP", "entry": entry, "stop": entry * 0.99, "tp2": entry * 1.1,
            "rr_tp2": rr, "last_price": last, "poi_proximal": entry, "poi_distal": entry * 0.99,
            "poi_tf": "4h", "warnings": []}
    item.update(extra)
    return item


def section(markdown, title):
    start = markdown.index("## " + title)
    end = markdown.find("\n## ", start + 1)
    return markdown[start:end if end != -1 else len(markdown)]


def main():
    assert config.ACTIONABLE_DISTANCE_PCT == {"crypto": 10.0, "forex": 1.0}
    synth.isolate_dirs()
    results = [
        row("NEARUSDT", "crypto", 100.0, 105.0),                 # %4.76 → actionable
        row("FARUSDT", "crypto", 100.0, 150.0, score=95),        # %33.3 → uzak
        row("EUR/USD", "forex", 1.1000, 1.1050),                 # %0.45 → actionable
        row("GBP/USD", "forex", 1.3000, 1.3300, score=90),       # %2.26 → uzak
        row("WATCHUSDT", "crypto", 100.0, 101.0, score=50),      # actionable, C → izleme
        row("EDGEUSDT", "crypto", 100.0, 110.0),                 # tam sınırda (%9.09) → actionable
    ]
    meta = {"scan_time_utc": datetime(2026, 10, 3, tzinfo=timezone.utc), "market": "all",
            "symbols_scanned": 6, "duration_seconds": 1, "error_count": 0, "errors": [], "symbols": []}
    paths = report.write_reports(results, meta)
    markdown = open(paths["md"], encoding="utf-8").read()
    ab, watch, far = (section(markdown, "A/B setup"), section(markdown, "İzleme listesi"),
                      section(markdown, "Uzak POI"))
    assert "NEARUSDT" in ab and "EUR/USD" in ab and "EDGEUSDT" in ab
    assert "FARUSDT" not in ab + watch and "GBP/USD" not in ab + watch
    assert "WATCHUSDT" in watch
    assert far.index("FARUSDT") < far.index("GBP/USD"), far  # puana göre sıralı (95 > 90)
    assert "actionable: 4, uzak: 2" in markdown
    rows = {r["symbol"]: r for r in csv.DictReader(open(paths["csv"], encoding="utf-8-sig"))}
    assert rows["FARUSDT"]["actionable"] == "false" and rows["NEARUSDT"]["actionable"] == "true"
    data = {r["symbol"]: r for r in json.load(open(paths["json"], encoding="utf-8"))["results"]}
    assert data["FARUSDT"]["actionable"] is False and data["EUR/USD"]["actionable"] is True
    # Mesafesi hesaplanamayan aday uzak sayılmaz.
    assert report._is_actionable({"symbol": "X/Y", "distance_pct": None})
    # Ekrandaki sayım yalnız actionable adaylardan; uzaklar ayrı.
    import argparse, contextlib, io
    import phantom_scan
    synth.isolate_dirs()
    original = phantom_scan._scan_symbol
    phantom_scan._scan_symbol = lambda symbol, market, no_cache, progress: (
        [dict(r, grade="A") for r in results if r["symbol"] == symbol], {"symbol": symbol})
    buffer = io.StringIO()
    try:
        args = argparse.Namespace(market="crypto", top=35, balance=None, risk=None, no_cache=False,
                                  show_all=False, symbols="NEARUSDT,FARUSDT,EDGEUSDT")
        with contextlib.redirect_stdout(buffer):
            phantom_scan.run_scan(args)
    finally:
        phantom_scan._scan_symbol = original
    assert "A: 2, B: 0, C: 0, Uzak: 1" in buffer.getvalue(), buffer.getvalue()
    print("Uzak POI'ler ayrı bölümde; actionable alanı CSV/JSON'da: GEÇTİ")
    print("test_step33: OK")


if __name__ == "__main__":
    main()
