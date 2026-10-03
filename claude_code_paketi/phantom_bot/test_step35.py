"""Adım 35: rapor biçimi — protected/targeted fiyat olarak, R:R/stop% yuvarlama, D1 konumu."""
import csv
import json
from datetime import datetime, timezone

import report
import synth
from test_step33 import row, section


def main():
    synth.isolate_dirs()
    item = row("EUR/USD", "forex", 1.13493, 1.12501, score=82, rr=4.996001, grade="A",
               rr_tp1=1.234567, stop_pips_or_pct=33.39999999999898, poi_rank=1)
    border = row("GBP/USD", "forex", 1.3000, 1.3010, score=80, rr=4.996, grade="A")
    border["poi_proximal"] = 1.3
    meta = {"scan_time_utc": datetime(2026, 10, 3, tzinfo=timezone.utc), "market": "forex",
            "symbols_scanned": 1, "duration_seconds": 1, "error_count": 0, "errors": [],
            "symbols": [{"symbol": "EUR/USD", "market": "forex", "htf_bias_d1": "BEARISH",
                         "htf_bias_h4": "BEARISH",
                         "protected": {"type": "high", "price": 1.137971234, "index": 146},
                         "targeted": {"type": "low", "price": 1.12159, "index": 154},
                         "premium_discount_d1": "Premium", "premium_discount": "Discount"}]}
    paths = report.write_reports([item, border], meta)
    markdown = open(paths["md"], encoding="utf-8").read()
    htf = section(markdown, "Sembol başına HTF")
    assert "{'type'" not in markdown and "'price'" not in markdown, htf
    assert "| 1.13797 |" in htf and "| 1.12159 |" in htf
    assert "| D1 konum | 4H konum |" in htf and "| Premium | Discount |" in htf
    assert "| 5.0 |" in section(markdown, "A/B") or "| 5.0 |" in section(markdown, "İzleme")
    # 4.996 → ekranda 5.0, ama karar ham değerle verilir: eşiğin altında kalır, A/B'ye girmez.
    assert "GBP/USD" not in section(markdown, "A/B") and "GBP/USD" in section(markdown, "İzleme")
    rows = {r["symbol"]: r for r in csv.DictReader(open(paths["csv"], encoding="utf-8-sig"))}
    assert rows["EUR/USD"]["rr_tp2"] == "5.0" and rows["EUR/USD"]["rr_tp1"] == "1.23"
    assert rows["EUR/USD"]["stop_pips_or_pct"] == "33.4"
    data = {r["symbol"]: r for r in json.load(open(paths["json"], encoding="utf-8"))["results"]}
    assert data["EUR/USD"]["rr_tp2"] == 5.0 and data["EUR/USD"]["stop_pips_or_pct"] == 33.4
    print("Rapor biçimi (seviye fiyatı, yuvarlama, D1 konumu): GEÇTİ")
    print("test_step35: OK")


if __name__ == "__main__":
    main()
