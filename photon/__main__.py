"""`python -m photon check [--config PATH] [--module M ...]` — config durum raporu."""
from __future__ import annotations

import argparse
import sys

from .config import DEFAULT_PATH, MODULES, find_required, load_config, validate_all
from .config.validator import collect_failures, format_errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="photon")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ck = sub.add_parser("check", help="config doğrula, modül durumlarını listele")
    ck.add_argument("--config", default=str(DEFAULT_PATH))
    ck.add_argument("--module", action="append", choices=list(MODULES),
                    help="verilirse bu modüller hazır değilse çıkış kodu 2")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
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


if __name__ == "__main__":
    raise SystemExit(main())
