"""Adım 10 sahte sonuçlarla rapor dosyası üretim testi."""
import os
import shutil
import tempfile
from datetime import datetime, timezone

import config
import report


def main():
    original_scans_dir = config.SCANS_DIR
    test_scans_dir = tempfile.mkdtemp(prefix="phantom_test_step10_")
    config.SCANS_DIR = test_scans_dir
    results = [
        {"scan_time_utc": "2026-10-01T12:00:00Z", "market": "forex", "symbol": "EUR/USD",
         "direction": "BULLISH", "htf_bias_d1": "BULLISH", "htf_bias_h4": "BULLISH",
         "poi_tf": "4h", "poi_stack": "1day,4h,1h", "poi_proximal": 1.1000,
         "poi_distal": 1.0950, "poi_eq": 1.0975, "poi_state": "FRESH", "status": "ENTRY1_READY",
         "entry_type": "confirmation", "entry": 1.0950, "stop": 1.0945,
         "stop_pips_or_pct": 5, "tp1": 1.1050, "tp2": 1.1200, "rr_tp1": 20,
         "rr_tp2": 50, "score": 88, "grade": "A", "premium_discount": "Discount",
         "sweep": True, "fvg": True, "inducement": True, "session_tag": "NYAM",
         "warnings": [], "last_price": 1.1010, "ltf_tf": "5m", "entry_restriction": ""},
        {"scan_time_utc": "2026-10-01T12:00:00Z", "market": "crypto", "symbol": "BTCUSDT",
         "direction": "BEARISH", "htf_bias_d1": "BEARISH", "htf_bias_h4": "BEARISH",
         "poi_tf": "1h", "poi_stack": "4h,1h", "poi_proximal": 84000, "poi_distal": 84500,
         "poi_eq": 84250, "poi_state": "TAPPED", "status": "TAPPED_NO_BOS", "entry_type": "risk",
         "entry": 84000, "stop": 85000, "stop_pips_or_pct": 1.19, "tp1": 82000,
         "tp2": 79000, "rr_tp1": 2, "rr_tp2": 5, "score": 66, "grade": "B",
         "premium_discount": "Premium", "sweep": False, "fvg": True, "inducement": False,
         "session_tag": "", "warnings": ["NEWS"], "last_price": 83000,
         "ltf_tf": "", "entry_restriction": "NEWS"},
        {"scan_time_utc": "2026-10-01T12:00:00Z", "market": "forex", "symbol": "GBP/USD",
         "direction": "BULLISH", "htf_bias_d1": "BULLISH", "htf_bias_h4": "UNDEFINED",
         "poi_tf": "1h", "poi_stack": "1h", "poi_proximal": 1.3000, "poi_distal": 1.2950,
         "poi_eq": 1.2975, "poi_state": "TAPPED", "status": "WAITING_TAP", "entry_type": "risk",
         "entry": 1.3000, "stop": 1.2945, "tp1": 1.3050, "tp2": 1.3200,
         "rr_tp1": 0.9, "rr_tp2": 3.6, "score": 52, "grade": "C",
         "premium_discount": "Discount", "sweep": False, "fvg": False,
         "inducement": False, "session_tag": "ASIA", "warnings": ["NO_TARGET"],
         "last_price": 1.3010, "entry_restriction": "ASIA"},
    ]
    meta = {"scan_time_utc": datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
            "market": "all", "symbols_scanned": 3, "duration_seconds": 4.2,
            "error_count": 0, "errors": [], "warnings": [],
            "symbols": [{"symbol": "EUR/USD", "htf_bias_d1": "BULLISH", "htf_bias_h4": "BULLISH",
                         "protected": 1.0950, "targeted": 1.1200, "premium_discount": "Discount"},
                        {"symbol": "BTCUSDT", "htf_bias_d1": "BEARISH", "htf_bias_h4": "BEARISH",
                         "protected": 84500, "targeted": 79000, "premium_discount": "Premium"},
                        {"symbol": "GBP/USD", "htf_bias_d1": "BULLISH", "htf_bias_h4": "UNDEFINED",
                         "protected": 1.295, "targeted": 1.32, "premium_discount": "Discount"}]}
    # Avoid creating cache/log folders outside this isolated report test.
    ensure_directories = report.utils.ensure_directories
    report.utils.ensure_directories = lambda: None
    try:
        paths = report.write_reports(results, meta)
        for kind, path in paths.items():
            assert os.path.isfile(path), "{} raporu oluşturulmadı".format(kind)
            print("{}: {}".format(kind, path))
        with open(paths["latest"], "r", encoding="utf-8") as handle:
            content = handle.read()
        assert "A/B setup'ları" in content and "İzleme listesi" in content
        assert "yatırım tavsiyesi değildir" in content
    finally:
        report.utils.ensure_directories = ensure_directories
        config.SCANS_DIR = original_scans_dir
        shutil.rmtree(test_scans_dir, ignore_errors=True)
    print("test_step10: OK — geçici rapor dosyaları temizlendi.")


if __name__ == "__main__":
    main()
