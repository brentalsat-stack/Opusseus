"""`python -m photon check [--config PATH] [--module M ...]` — config durum raporu."""
from __future__ import annotations

import argparse
import sys
from datetime import date

from .config import DEFAULT_PATH, MODULES, find_required, load_config, validate_all
from .config.validator import collect_failures, format_errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="photon")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="config doğrula, modül durumlarını listele")
    ck.add_argument("--config", default=str(DEFAULT_PATH))
    ck.add_argument("--module", action="append", choices=list(MODULES),
                    help="verilirse bu modüller hazır değilse çıkış kodu 2")
    for name, helptext in (("fetch", "M1 bid/ask indir → önbellek (+ isteğe bağlı CSV)"),
                           ("data-check", "önbellekteki M1/M15 serisini doğrula (düzeltmeden raporla)")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--config", default=str(DEFAULT_PATH))
        sp.add_argument("--source", choices=["OANDA_PRACTICE", "DUKASCOPY"],
                        help="verilmezse config data.backtest.primary")
        sp.add_argument("--pair", default=None, help="verilmezse config pairs[0]")
        sp.add_argument("--start", type=date.fromisoformat, required=True)
        sp.add_argument("--end", type=date.fromisoformat, required=True, help="dahil")
        if name == "fetch":
            sp.add_argument("--csv", help="indirilen aralığı CSV'ye yaz")
    st = sub.add_parser("structure", help="yapı olaylarını bul: CSV + işaretli grafik (doğrulama)")
    st.add_argument("--config", default=str(DEFAULT_PATH))
    st.add_argument("--source", choices=["OANDA_PRACTICE", "DUKASCOPY"])
    st.add_argument("--pair")
    st.add_argument("--tf", required=True, choices=["D1", "H4", "M15", "M1"])
    st.add_argument("--start", type=date.fromisoformat, required=True)
    st.add_argument("--end", type=date.fromisoformat, required=True, help="dahil")
    st.add_argument("--seed", required=True, help="başlangıç yapısı YAML (cold start tanımsız: Q-S01)")
    st.add_argument("--out", default="structure_out")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.cmd in ("fetch", "data-check"):
        return _data_cmd(cfg, args)
    if args.cmd == "structure":
        return _structure_cmd(cfg, args)
    reports = validate_all(cfg)
    for name, r in reports.items():
        print(f"{'READY  ' if r.ok else 'BLOCKED'} {name}")
    pending = find_required(cfg.raw)
    print(f"\nBekleyen (REQUIRED) alanlar: {len(pending)}")
    for p in pending:
        print(f"  - {p}")
    if args.module:
        bad = collect_failures(cfg, *args.module)
        if bad:
            print("\n" + format_errors(bad), file=sys.stderr)
            return 2
    return 0


def _structure_cmd(cfg, args) -> int:
    from pathlib import Path

    from .data import tools
    from .data.models import PriceSide, Timeframe
    from .data.resample import BoundarySpec, resample
    from .logging_setup import setup_from_config
    from .structure.params import StructureParams
    from .structure.report import load_seed_yaml, plot_events, run_structure, write_events_csv

    setup_from_config(cfg)
    source = args.source or cfg.get("data.backtest.primary")
    pair = args.pair or cfg.pairs[0]
    tf = Timeframe(args.tf)
    cfg.require("data_boundaries")
    start, end = tools.day_range(args.start, args.end)
    m1 = tools.load_m1(cfg, source, pair, start, end)
    if not m1:
        print("önbellekte M1 yok; önce `photon fetch` çalıştırın", file=sys.stderr)
        return 2
    spec = BoundarySpec.from_config(cfg)
    qc = m1 if tf is Timeframe.M1 else resample(m1, tf, spec)
    side = PriceSide(cfg.get("candle_price_side"))
    candles = [c.to_candle(side) for c in qc if c.complete]   # yalnızca kapanmış mumlar
    seed, hist = load_seed_yaml(args.seed, candles)
    eng = run_structure(candles, StructureParams.from_config(cfg, pair, tf), seed, hist)
    out = Path(args.out)
    n = write_events_csv(eng.events, out / f"{pair}_{tf.value}_structure.csv")
    plot_events(candles, eng.events, out / f"{pair}_{tf.value}_structure.png")
    print(f"{n} olay → {out}/")
    return 0


def _data_cmd(cfg, args) -> int:
    import logging

    from .data import tools
    from .data.models import Timeframe
    from .data.resample import resample
    from .data.validate import check_series
    from .logging_setup import setup_from_config

    setup_from_config(cfg)
    source = args.source or cfg.get("data.backtest.primary")
    pair = args.pair or cfg.pairs[0]
    start, end = tools.day_range(args.start, args.end)
    if args.cmd == "fetch":
        n = tools.fetch(cfg, source, pair, start, end)
        print(f"{source} {pair}: {n} yeni M1 mum önbelleğe yazıldı")
        if args.csv:
            print(f"CSV: {tools.export_csv(tools.load_m1(cfg, source, pair, start, end), args.csv)} satır → {args.csv}")
        return 0
    m1 = tools.load_m1(cfg, source, pair, start, end)
    rep1 = check_series(m1, Timeframe.M1)
    print(rep1.summary())
    rep1.log()
    rep15 = check_series(resample(m1, Timeframe.M15), Timeframe.M15)
    print(rep15.summary())
    logging.getLogger("photon").info("data-check %s %s tamam", source, pair)
    return 0 if rep1.ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
