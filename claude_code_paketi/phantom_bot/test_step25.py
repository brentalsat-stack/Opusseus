"""Adım 25: last_price ve distance_pct sütunları CSV/JSON/Markdown'da (filtre eklenmez)."""
import csv
import glob
import json
import os
from datetime import datetime, timezone

import config
import report
import synth


def main():
    root = synth.isolate_dirs()
    item = {"market": "forex", "symbol": "EUR/USD", "direction": "BEARISH", "score": 82, "grade": "A",
            "status": "WAITING_TAP", "entry": 1.13493, "stop": 1.13827, "tp2": 1.12159,
            "rr_tp2": 5.2, "last_price": 1.12501, "poi_proximal": 1.13493, "poi_distal": 1.13797,
            "warnings": []}
    far = dict(item, symbol="GBP/USD", poi_proximal=1.3, poi_distal=1.31, entry=1.5, last_price=1.0)
    no_price = dict(item, symbol="AUD/USD", poi_proximal=0.7, poi_distal=0.71, last_price=None)
    meta = {"scan_time_utc": datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc), "market": "forex",
            "symbols_scanned": 3, "duration_seconds": 1, "error_count": 0, "errors": [], "symbols": []}
    paths = report.write_reports([item, far, no_price], meta)

    rows = {r["symbol"]: r for r in csv.DictReader(open(paths["csv"], encoding="utf-8-sig"))}
    assert "last_price" in rows["EUR/USD"] and "distance_pct" in rows["EUR/USD"]
    expected = round(abs(1.13493 - 1.12501) / 1.12501 * 100, 2)
    assert float(rows["EUR/USD"]["distance_pct"]) == expected == 0.88, rows["EUR/USD"]
    assert float(rows["GBP/USD"]["distance_pct"]) == 50.0
    assert rows["AUD/USD"]["distance_pct"] == ""
    data = json.load(open(paths["json"], encoding="utf-8"))
    assert {r["symbol"]: r["distance_pct"] for r in data["results"]}["EUR/USD"] == 0.88
    markdown = open(paths["md"], encoding="utf-8").read()
    assert "| Son fiyat | Mesafe % |" in markdown and "1.12501" in markdown and "0.88" in markdown
    # Filtre eklenmedi: uzak aday da listede.
    assert "GBP/USD" in rows
    print("last_price ve distance_pct CSV/JSON/MD: GEÇTİ")
    print("test_step25: OK")


if __name__ == "__main__":
    main()
