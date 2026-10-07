"""Tek komutla backtest: veri indir → replay → simülasyon → rapor.

Kullanım (Windows Komut İstemi):  python backtest\\run_backtest.py --days 180 --step 4
İlk deneme için:                  python backtest\\run_backtest.py --smoke
"""
import argparse
import multiprocessing
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import data_futures  # noqa: E402
import fetch_history  # noqa: E402
import replay  # noqa: E402
import report_bt  # noqa: E402
import simulate  # noqa: E402
import utils  # noqa: E402

SMOKE_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
SMOKE_DAYS = 7


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Phantom SMC backtest (Binance USDⓈ-M perpetual verisi)")
    parser.add_argument("--days", type=int, default=config.BT_DAYS, help="Replay edilen gün sayısı (varsayılan {})".format(config.BT_DAYS))
    parser.add_argument("--step", type=float, default=config.BT_STEP_HOURS, help="Replay adımı, saat (varsayılan {})".format(config.BT_STEP_HOURS))
    parser.add_argument("--symbols", default=None, help="Virgülle ayrılmış semboller (varsayılan: config.BACKTEST_SYMBOLS)")
    parser.add_argument("--smoke", action="store_true",
                        help="Hızlı deneme: 2 sembol, 7 gün; fapi yanıt şemasını (yalnız alan adları) yazar")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                        help="Paralel süreç sayısı (varsayılan: çekirdek - 1)")
    parser.add_argument("--skip-fetch", action="store_true", help="Veri indirmeyi atla (yalnız CSV önbelleği)")
    parser.add_argument("--force-replay", action="store_true", help="Replay önbelleğini yok say")
    parser.add_argument("--data-dir", default=config.BT_DATA_DIR)
    parser.add_argument("--results-dir", default=config.BT_RESULTS_DIR)
    parser.add_argument("--end-ts", type=int, default=None, help="Veri bitiş zamanı (epoch sn); tekrarlanabilir koşu için")
    args = parser.parse_args(argv)
    if args.days < 1 or args.step <= 0 or args.workers < 1:
        parser.error("--days, --step ve --workers pozitif olmalı")
    return args


def log_schema(schema, results_dir, print_fn):
    """Ham fapi yanıtlarının alan adlarını (değer değil) results/schema_log.txt dosyasına yazar."""
    if not schema.lines:
        return None
    os.makedirs(results_dir, exist_ok=True)
    path = os.path.join(results_dir, "schema_log.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(schema.lines) + "\n")
    print_fn("Şema günlüğü: {}".format(path))
    return path


def _safe_console():
    """Windows konsolu/yönlendirmesi UTF-8 olmayabilir (Ş, ⓈM karakterleri): hata yerine '?' yaz."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None, request=None, print_fn=print):
    _safe_console()
    args = parse_args(argv)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] if args.symbols else list(config.BACKTEST_SYMBOLS)
    days = args.days
    if args.smoke:
        symbols, days = SMOKE_SYMBOLS, SMOKE_DAYS
    request = request or fetch_history.default_request
    started = time.monotonic()
    schema = fetch_history.SchemaLog(limit=3 if args.smoke else 0)
    print_fn("Phantom backtest: {} sembol, {} gün, adım {} saat, {} işçi".format(len(symbols), days, args.step, args.workers))
    print_fn("Veri klasörü: {}".format(args.data_dir))

    if not args.skip_fetch:
        try:
            if args.smoke:
                payload, _ = request(config.BINANCE_FUTURES_EXCHANGE_INFO_PATH, {})
                schema.record("exchangeInfo", payload)
            print_fn("1/4 Veri indirme (yalnızca eksik kısım indirilir)")
            fetch_history.fetch_all(symbols, days, end_s=args.end_ts, data_dir=args.data_dir, request=request,
                                    schema=schema if args.smoke else None, print_fn=print_fn)
        except data_futures.FuturesRegionBlocked as exc:
            print_fn("HATA: {}".format(utils.mask_secrets(exc)))
            return 2
        except data_futures.FuturesAPIError as exc:
            print_fn("HATA: {}".format(utils.mask_secrets(exc)))
            return 3
    log_schema(schema, args.results_dir, print_fn)
    print_fn("   veri aşaması: {:.0f} sn".format(time.monotonic() - started))

    phase = time.monotonic()
    print_fn("2/4 Replay (look-ahead'siz tarama)")
    setups, window = replay.replay_all(symbols, args.data_dir, days, args.step, workers=args.workers,
                                       results_dir=args.results_dir, force=args.force_replay, print_fn=print_fn)
    print_fn("   {} tekil setup; replay aşaması: {:.0f} sn".format(len(setups), time.monotonic() - phase))

    phase = time.monotonic()
    print_fn("3/4 Simülasyon")
    trades = simulate.simulate_all(setups, symbols, args.data_dir, workers=args.workers, print_fn=print_fn)
    print_fn("   simülasyon aşaması: {:.0f} sn".format(time.monotonic() - phase))

    print_fn("4/4 Rapor")
    paths = report_bt.write_reports(trades, window, args.results_dir, {"symbols": symbols})
    rows = report_bt.flatten(trades)
    for mode in report_bt.MODES:
        for variant in report_bt.VARIANTS:
            s = report_bt.stats(report_bt.select(rows, mode, variant))
            print_fn("   {:12s} {:16s} işlem {:4d}  win {:5.1f}%  ort. R net {:+.3f}  toplam R net {:+.2f}  maxDD {:.2f}".format(
                mode, report_bt.VARIANT_LABEL[variant], s["n"], s["winrate"], s["avg_net"], s["total_net"], s["max_dd"]))
    for name, path in paths.items():
        print_fn("   {}: {}".format(name, path))
    print_fn("Toplam süre: {:.0f} sn".format(time.monotonic() - started))
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
