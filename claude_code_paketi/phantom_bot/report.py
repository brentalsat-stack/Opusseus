"""Turkish Markdown, CSV and JSON scan report writers."""
import csv
import json
import math
import os
from datetime import datetime, timezone

import config
import utils


CSV_COLUMNS = [
    "scan_time_utc", "market", "symbol", "direction", "htf_bias_d1", "htf_bias_h4",
    "poi_tf", "poi_stack", "poi_proximal", "poi_distal", "poi_eq", "poi_state",
    "status", "entry_type", "entry", "stop", "stop_pips_or_pct", "tp1", "tp2",
    "rr_tp1", "rr_tp2", "score", "grade", "premium_discount", "sweep", "fvg",
    "inducement", "session_tag", "warnings", "last_price", "poi_rank", "ltf_tf",
    "entry_restriction", "distance_pct", "actionable",
]


def _utc_datetime(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _score(item):
    try:
        return float(item.get("score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _rr(item):
    try:
        value = item.get("rr_tp2")
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _grade(item):
    explicit = str(item.get("grade", "")).strip().upper()
    if explicit:
        return explicit
    score = _score(item)
    if score >= config.SCORE_GRADE_A:
        return "A"
    if score >= config.SCORE_GRADE_B:
        return "B"
    if score >= config.SCORE_GRADE_C:
        return "C"
    return "-"


def _round2(value):
    """Display rounding for ratios; decisions (A/B, R:R threshold) keep the raw value."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 2)
    return value


def _display_row(item):
    row = dict(item)
    for field in ("rr_tp1", "rr_tp2", "stop_pips_or_pct"):
        if field in row:
            row[field] = _round2(row[field])
    return row


def _level_price(value):
    """Price of a structure level that may be a {"type","price","index"} record."""
    return value.get("price") if isinstance(value, dict) else value


def _format_price(value, market, symbol):
    """Round report prices to the market's requested display precision."""
    if value in (None, "") or isinstance(value, bool):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(number):
        return value
    market_text = str(market or "").lower()
    symbol_text = str(symbol or "").upper()
    if market_text == "crypto":
        if number == 0:
            return 0.0
        decimals = 6 - int(math.floor(math.log10(abs(number)))) - 1
        return round(number, decimals)
    decimals = 3 if "JPY" in symbol_text or "XAU" in symbol_text else 5
    return round(number, decimals)


def _distance_pct(item):
    """|entry − last_price| / last_price × 100, or None when either is missing."""
    try:
        entry, last = float(item.get("entry")), float(item.get("last_price"))
    except (TypeError, ValueError):
        return None
    return round(abs(entry - last) / last * 100.0, 2) if last else None


def _market_of(item):
    symbol = str(item.get("symbol", ""))
    return str(item.get("market") or ("forex" if "/" in symbol or "XAU" in symbol.upper() else "crypto")).lower()


def _is_actionable(item):
    """True when the entry is within ACTIONABLE_DISTANCE_PCT of the last price.

    Without a computable distance the candidate cannot be judged far, so it stays actionable.
    """
    distance = item.get("distance_pct")
    limit = config.ACTIONABLE_DISTANCE_PCT.get(_market_of(item))
    if distance in (None, "") or limit is None:
        return True
    return float(distance) <= float(limit)


def _has_no_target(item):
    if item.get("tp2") is None:
        return True
    warnings = item.get("warnings", [])
    if isinstance(warnings, str):
        warnings = [part.strip() for part in warnings.split(",")]
    return any(str(warning).strip().upper() == "NO_TARGET" for warning in warnings or [])


def _candidate_key(item):
    return (str(item.get("symbol", "")), str(item.get("direction", "")),
            str(item.get("poi_tf", "")), str(item.get("poi_proximal", "")),
            str(item.get("poi_distal", "")))


def _qualifies_ab(item):
    rr = _rr(item)
    return (_grade(item) in ("A", "B") and rr is not None
            and rr >= float(config.MIN_RR_TP2) and not _has_no_target(item))


def _json_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return "Evet" if value else "Hayır"
    return value


def _limit_candidates(results, meta):
    show_all = bool(meta.get("show_all", False))
    minimum = float(config.SCORE_MIN_REPORT)
    eligible = [dict(item) for item in results if show_all or _score(item) >= minimum]
    groups = {}
    for item in eligible:
        key = (str(item.get("symbol", "")), str(item.get("direction", "")))
        groups.setdefault(key, []).append(item)
    limited = []
    for rows in groups.values():
        rows.sort(key=lambda item: (-_score(item),
                                    abs(float(item.get("poi_proximal", 0) or 0) - float(item.get("last_price", 0) or 0)),
                                    str(item.get("poi_tf", ""))))
        for rank, item in enumerate(rows[:int(config.MAX_POI_PER_SYMBOL_DIR)], 1):
            item["poi_rank"] = rank
            item["distance_pct"] = _distance_pct(item)  # raw values, before price rounding
            item["actionable"] = _is_actionable(item)
            item["grade"] = _grade(item) if _score(item) >= minimum else "-"
            symbol = item.get("symbol", "")
            market = item.get("market", "forex" if "/" in str(symbol) or "XAU" in str(symbol).upper() else "crypto")
            for field in ("poi_proximal", "poi_distal", "poi_eq", "entry", "stop",
                          "tp1", "tp2", "last_price"):
                if field in item:
                    item[field] = _format_price(item[field], market, symbol)
            limited.append(item)
    limited.sort(key=lambda item: (-_score(item), str(item.get("symbol", "")),
                                   str(item.get("direction", "")), int(item.get("poi_rank", 1))))
    return limited


def _md(value):
    if value is None or value == "":
        return "—"
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text


def _candidate_table(items, empty="Bu bölümde setup yok"):
    lines = ["| Sembol | Yön | Rank | Puan | Not | Durum | Giriş | Stop | TP2 | R:R TP2 | Son fiyat | Mesafe % |",
             "|---|---|---:|---:|:---:|---|---:|---:|---:|---:|---:|---:|"]
    for item in items:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            _md(item.get("symbol")), _md(item.get("direction")), _md(item.get("poi_rank")),
            _md(item.get("score")), _md(_grade(item)), _md(item.get("status")),
            _md(item.get("entry")), _md(item.get("stop")), _md(item.get("tp2")),
            _md(_round2(item.get("rr_tp2"))), _md(item.get("last_price")), _md(item.get("distance_pct"))))
    if not items:
        lines.append("| — | — | — | — | — | {} | — | — | — | — | — | — |".format(empty))
    return lines


def _build_markdown(results, meta, scan_time):
    far = sorted((item for item in results if not item.get("actionable", True)),
                 key=lambda item: -_score(item))
    results = [item for item in results if item.get("actionable", True)]
    a_b = [item for item in results if _qualifies_ab(item)
           and int(item.get("poi_rank", 1)) == 1]
    a_b_keys = {_candidate_key(item) for item in a_b}
    watch = [item for item in results if _score(item) >= config.SCORE_MIN_REPORT and
             _candidate_key(item) not in a_b_keys and
             (_grade(item) == "C" or _rr(item) is None or
              _rr(item) < float(config.MIN_RR_TP2) or _has_no_target(item))]
    shown_keys = a_b_keys | {_candidate_key(item) for item in watch}
    # rank 2+ actionable candidates that fit neither table above (e.g. a B-grade rank 2 with good R:R)
    others = [item for item in results if int(item.get("poi_rank", 1)) >= 2
              and _score(item) >= config.SCORE_MIN_REPORT
              and _candidate_key(item) not in shown_keys]
    symbols = meta.get("symbols", meta.get("htf_status", [])) or []
    if isinstance(symbols, dict):
        symbols = [dict(value, symbol=key) if isinstance(value, dict) else {"symbol": key, "htf_status": value}
                   for key, value in symbols.items()]
    if not symbols:
        seen = {}
        for item in results:
            symbol = item.get("symbol")
            if symbol and symbol not in seen:
                seen[symbol] = {"symbol": symbol, "htf_bias_d1": item.get("htf_bias_d1"),
                                "htf_bias_h4": item.get("htf_bias_h4"),
                                "protected": item.get("protected"), "targeted": item.get("targeted"),
                                "premium_discount": item.get("premium_discount")}
        symbols = list(seen.values())

    lines = ["# Phantom SMC Tarama Raporu", "", "## Özet", "",
             "- Tarama zamanı (UTC): {}".format(scan_time.strftime("%Y-%m-%d %H:%M:%S")),
             "- Piyasa: {}".format(_md(meta.get("market", "all"))),
             "- Taranan sembol: {}".format(_md(meta.get("symbols_scanned", len(symbols)))),
             "- Setup adayı: {} (actionable: {}, uzak: {})".format(
                 len(results) + len(far), len(results), len(far)),
             "- Hata sayısı: {}".format(_md(meta.get("error_count", len(meta.get("errors", []))))),
             "- Süre: {} sn".format(_md(meta.get("duration_seconds", "—"))), "",
             "## A/B setup'ları", ""]
    lines.extend(_candidate_table(a_b))
    lines.extend(["", "## İzleme listesi (C veya TP2 R:R eşiğinin altında)", ""])
    lines.extend(_candidate_table(watch))
    lines.extend(["", "## Diğer adaylar (rank 2 ve sonrası)", ""])
    lines.extend(_candidate_table(others, empty="Diğer aday yok"))
    lines.extend(["", "## Uzak POI'ler (giriş son fiyattan uzak; puana göre)", ""])
    lines.extend(_candidate_table(far, empty="Uzak POI yok"))
    lines.extend(["", "## Sembol başına HTF durumu", "",
                  "| Sembol | D1 bias | 4H bias | Protected | Targeted | D1 konum | 4H konum |",
                  "|---|---|---|---:|---:|---|---|"])
    for item in symbols:
        if not isinstance(item, dict):
            item = {"symbol": str(item)}
        symbol = item.get("symbol", "")
        market = item.get("market", "forex" if "/" in str(symbol) or "XAU" in str(symbol).upper() else "crypto")
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            _md(item.get("symbol")), _md(item.get("htf_bias_d1", item.get("bias_d1"))),
            _md(item.get("htf_bias_h4", item.get("bias_h4"))),
            _md(_format_price(_level_price(item.get("protected", item.get("protected_level"))), market, symbol)),
            _md(_format_price(_level_price(item.get("targeted", item.get("targeted_level"))), market, symbol)),
            _md(item.get("premium_discount_d1")),
            _md(item.get("premium_discount", item.get("price_position")))))
    if not symbols:
        lines.append("| — | — | — | — | — | — | HTF verisi yok |")

    errors = list(meta.get("errors", []) or [])
    warnings = list(meta.get("warnings", []) or [])
    for item in results:
        raw = item.get("warnings", [])
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.split(",") if part.strip()]
        for warning in raw or []:
            warnings.append("{}: {}".format(item.get("symbol", ""), warning))
    lines.extend(["", "## Hata ve uyarı günlüğü", ""])
    lines.extend("- HATA: {}".format(_md(value)) for value in errors)
    lines.extend("- UYARI: {}".format(_md(value)) for value in warnings)
    if not errors and not warnings:
        lines.append("- Hata veya uyarı yok.")
    lines.extend(["", "## Bilgilendirme", "",
                  "Bu çıktı otomatik teknik analiz taramasıdır, yatırım tavsiyesi değildir. İşlem kararı kullanıcıya aittir.",
                  "", "Yönetim notu: TP1'de riske eşit kısmi kâr (1R), ilgili swing kırılınca BE. Hedefte %75–80 kapat.",
                  ""])
    return "\n".join(lines)


def write_reports(results, meta):
    """Write timestamped Markdown/CSV/JSON files and a latest.md copy.

    Returns a dictionary of output file paths. ``results`` should contain
    setup dictionaries; ``meta`` may include scan metadata and HTF rows.
    """
    if not isinstance(results, (list, tuple)):
        raise TypeError("results list olmalı")
    meta = dict(meta or {})
    scan_time = _utc_datetime(meta.get("scan_time_utc"))
    utils.ensure_directories()
    output_dir = config.SCANS_DIR
    os.makedirs(output_dir, exist_ok=True)
    stamp = scan_time.strftime("%Y-%m-%d_%H%M_UTC")
    md_path = os.path.join(output_dir, "scan_{}.md".format(stamp))
    csv_path = os.path.join(output_dir, "scan_{}.csv".format(stamp))
    json_path = os.path.join(output_dir, "scan_{}.json".format(stamp))
    latest_path = os.path.join(output_dir, "latest.md")

    rows = _limit_candidates(results, meta)
    markdown = _build_markdown(rows, meta, scan_time)
    with open(md_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(markdown)
    with open(latest_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(markdown)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for item in rows:
            display = _display_row(item)
            record = {column: _json_value(display.get(column)) for column in CSV_COLUMNS}
            record["actionable"] = "true" if item.get("actionable", True) else "false"
            writer.writerow(record)
    payload = {"scan_time_utc": scan_time.isoformat().replace("+00:00", "Z"),
               "meta": meta, "results": [_display_row(item) for item in rows]}
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    return {"md": md_path, "csv": csv_path, "json": json_path, "latest": latest_path}
