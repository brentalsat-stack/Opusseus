"""Emir/pozisyon simülasyonu (5m mumlarla) ve maliyet hesabı. Tüm sonuçlar R cinsindendir (1R sabit risk, kaldıraç yok).

Varsayımlar (README_BACKTEST.md'de de yazılı):
- Limit emir giriş seviyesinde dolar (iyileşme yok). Dolum mumunda yalnızca STOP kontrol edilir; TP/BE sonraki mumdan başlar.
- Aynı 5m mumunda stop ve hedef birlikte görülürse STOP kazanır.
- TP çıkışı MAKER; STOP, BE ve TIMEOUT çıkışları TAKER + kayma. Giriş MAKER.
- Funding: pozisyon açıkken geçen her funding anı için ``yön × oran × açık oran × giriş / stop mesafesi`` R.
"""
import bisect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import indicators  # noqa: E402
import orderblocks  # noqa: E402
import replay  # noqa: E402
import signals  # noqa: E402

VARIANTS = ("TP2", "TP1BE")
MODES = ("risk", "confirmation")
FIVE = 300
MIN_STOP_PCT = 0.005  # min stop hipotezi (a): giriş fiyatının %0.5'i


def _params():
    return {"touch_expiry": config.BT_TOUCH_EXPIRY_HOURS * 3600,
            "confirm_fill": config.BT_CONFIRM_FILL_HOURS * 3600,
            "confirm_wait": config.BT_CONFIRM_WAIT_HOURS * 3600,
            "max_hold": config.BT_MAX_HOLD_DAYS * 86400,
            "maker": config.BT_FEE_MAKER_PCT / 100.0, "taker": config.BT_FEE_TAKER_PCT / 100.0,
            "slip": config.BT_SLIPPAGE_PCT / 100.0}


def _sign(direction):
    return 1 if str(direction).upper() == "BULLISH" else -1


# ------------------------------------------------------------------ emir dolumu
def resolve_order(rows, times, start_t, direction, entry, stop, tp2, distal, deadline_t):
    """Limit emrin akıbeti. Dönüş: (durum, mum_indeksi).

    Durumlar: FILLED, CANCEL_TP2, CANCEL_INVALID, EXPIRED, PENDING_END (veri bitti).
    Dolum her iptal koşulundan önce kontrol edilir (aynı mumda dolum + iptal = dolum).
    """
    sign = _sign(direction)
    index = bisect.bisect_left(times, start_t)
    while index < len(rows):
        t, o, h, low, c, v = rows[index]
        if t >= deadline_t:
            return "EXPIRED", index
        if (low <= entry) if sign > 0 else (h >= entry):
            return "FILLED", index
        if tp2 is not None and ((h >= tp2) if sign > 0 else (low <= tp2)):
            return "CANCEL_TP2", index
        if distal is not None and ((c < distal) if sign > 0 else (c > distal)):
            return "CANCEL_INVALID", index
        index += 1
    return "PENDING_END", len(rows) - 1


# ------------------------------------------------------------------ pozisyon yönetimi
def manage_position(rows, fill_index, direction, entry, stop, tp1, tp2, variant, max_hold):
    """Dolumdan sonra çıkışı simüle eder. Dönüş: bacaklar [(ağırlık, fiyat, tür, kapanış_t)].

    Türler: TP (maker), STOP/BE/TIMEOUT (taker + kayma). TP2 varyantında tp1 yok sayılır;
    TP1BE'de TP1'de %50 kapanır, stop girişe (BE) taşınır.
    """
    sign = _sign(direction)
    use_tp1 = variant == "TP1BE" and tp1 is not None
    fill_t = rows[fill_index][0]
    legs = []
    remaining = 1.0
    current_stop = stop
    state_after_tp1 = False
    index = fill_index
    last = len(rows) - 1
    while index <= last:
        t, o, h, low, c, v = rows[index]
        close_t = t + FIVE
        stop_hit = (low <= current_stop) if sign > 0 else (h >= current_stop)
        if index == fill_index:
            if stop_hit:  # dolum mumunda yalnızca stop
                legs.append((remaining, current_stop, "STOP", close_t))
                return legs
            index += 1
            continue
        if stop_hit:  # stop önceliği (aynı mumda hedef de olsa)
            legs.append((remaining, current_stop, "BE" if state_after_tp1 else "STOP", close_t))
            return legs
        hit_tp2 = (h >= tp2) if sign > 0 else (low <= tp2)
        if use_tp1 and not state_after_tp1:
            hit_tp1 = (h >= tp1) if sign > 0 else (low <= tp1)
            if hit_tp2:
                legs.append((0.5, tp1, "TP", close_t))
                legs.append((0.5, tp2, "TP", close_t))
                return legs
            if hit_tp1:
                legs.append((0.5, tp1, "TP", close_t))
                remaining = 0.5
                current_stop = entry
                state_after_tp1 = True
        elif hit_tp2:
            legs.append((remaining, tp2, "TP", close_t))
            return legs
        if t - fill_t >= max_hold:
            legs.append((remaining, c, "TIMEOUT", close_t))
            return legs
        index += 1
    # veri bitti: kalan pozisyon son kapanıştan kapatılır (TIMEOUT, veri sonu işaretli)
    t, o, h, low, c, v = rows[last]
    legs.append((remaining, c, "TIMEOUT", t + FIVE))
    return legs


# ------------------------------------------------------------------ maliyet
def trade_result(direction, entry, stop, legs, fill_t, funding_rows, params=None):
    """Bacaklardan brüt/net R ve maliyet bileşenleri."""
    p = params or _params()
    sign = _sign(direction)
    risk = abs(entry - stop)
    gross = slip_cost = fee_cost = 0.0
    fee_cost += p["maker"] * entry / risk  # limit giriş
    exit_prices = []
    for weight, price, kind, close_t in legs:
        gross += weight * sign * (price - entry) / risk
        if kind == "TP":
            effective, fee = price, p["maker"]
        else:
            effective = price * (1.0 - sign * p["slip"])
            fee = p["taker"]
            slip_cost += weight * abs(price - effective) / risk
        fee_cost += weight * fee * effective / risk
        exit_prices.append(effective)
    funding_cost = 0.0
    last_close = max(close_t for _, _, _, close_t in legs)
    times = [row[0] for row in funding_rows]
    lo = bisect.bisect_right(times, fill_t)
    hi = bisect.bisect_right(times, last_close)
    for ftime, rate in funding_rows[lo:hi]:
        open_fraction = sum(weight for weight, _, _, close_t in legs if close_t >= ftime)
        funding_cost += sign * rate * open_fraction * entry / risk
    net = gross - slip_cost - fee_cost - funding_cost
    kinds = [leg[2] for leg in legs]
    if "TIMEOUT" in kinds:
        reason = "TIMEOUT"
    elif kinds == ["TP", "TP"]:
        reason = "TP1_TP2"
    elif "BE" in kinds:
        reason = "TP1_BE"
    elif kinds == ["STOP"]:
        reason = "STOP"
    else:
        reason = "TP2"
    return {"exit_reason": reason, "exit_t": last_close, "r_gross": gross, "r_net": net,
            "fee_r": fee_cost, "slip_r": slip_cost, "funding_r": funding_cost,
            "hold_hours": (last_close - fill_t) / 3600.0}


# ------------------------------------------------------------------ setup simülasyonu
def _base(record, mode):
    return {"mode": mode, "symbol": record["symbol"], "key": record["key"], "direction": record["direction"],
            "poi_tf": record["poi_tf"], "grade": record["grade"], "score": record["score"],
            "first_seen_t": record["first_seen_t"], "actionable": record.get("actionable", True),
            "distance_pct": record.get("distance_pct"), "market": record.get("market", "crypto"),
            "score_breakdown": record.get("score_breakdown")}


R3_MULTIPLE = 3.0  # sabit R hedef hipotezi: giriş ± 3 × orijinal stop mesafesi


def _outcome(record, rows, index, entry, stop, tp1, tp2, variant, fill_t, data, params):
    legs = manage_position(rows, index, record["direction"], entry, stop, tp1, tp2, variant, params["max_hold"])
    outcome = trade_result(record["direction"], entry, stop, legs, fill_t, data.funding, params)
    outcome["data_end"] = outcome["exit_reason"] == "TIMEOUT" and legs[-1][3] >= rows[-1][0] + FIVE
    return outcome


def _run_order(record, mode, data, order_t, entry, stop, tp1, tp2, valid_until, params, extra=None,
               min_stops=None):
    """Emri yerleştirip dolum + yönetim sonuçlarını üretir.

    Ana sonuç (``variants``: TP2 ve TP1BE) mevcut stratejidir. Ek hipotezler:
    ``r3`` — TP2 yerine sabit 3R hedef (kendi iptal/dolum çözümüyle);
    ``minstop`` — ``min_stops`` {ad: asgari stop mesafesi (fiyat)}; yalnızca confirmation için verilir,
    stop gerekirse genişler (giriş ve hedefler aynı), R yeniden hesaplanır.
    """
    rows, times = data.rows["5m"], data.times["5m"]
    result = _base(record, mode)
    result.update(extra or {})
    result.update({"order_t": order_t, "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2})
    risk = abs(entry - stop)
    sign = _sign(record["direction"])
    if risk > 0:
        result["stop_pct"] = risk / entry * 100.0
        result["r3"] = _run_r3(record, data, order_t, entry, stop, sign, risk, valid_until, params)
    if tp2 is None or risk <= 0:
        result["status"] = "NO_TARGET"
        return result
    result["rr_tp2"] = abs(tp2 - entry) / risk
    result["rr_tp1"] = abs(tp1 - entry) / risk if tp1 is not None else None
    status, index = resolve_order(rows, times, order_t, record["direction"], entry, stop, tp2,
                                  record["poi_distal"], valid_until)
    result["status"] = status
    if status != "FILLED":
        return result
    fill_t = rows[index][0]
    result["fill_t"] = fill_t
    result["variants"] = {variant: _outcome(record, rows, index, entry, stop, tp1, tp2, variant, fill_t, data, params)
                          for variant in VARIANTS}
    if min_stops:
        result["minstop"] = {}
        for name, distance in sorted(min_stops.items()):
            if distance is None or distance <= risk * (1 + 1e-12):
                result["minstop"][name] = {"changed": False, "stop": stop, "stop_pct": result["stop_pct"],
                                           "rr_tp2": result["rr_tp2"], "variants": result["variants"]}
                continue
            new_stop = entry - sign * distance
            result["minstop"][name] = {
                "changed": True, "stop": new_stop, "stop_pct": distance / entry * 100.0,
                "rr_tp2": abs(tp2 - entry) / distance,
                "variants": {variant: _outcome(record, rows, index, entry, new_stop, tp1, tp2, variant, fill_t,
                                               data, params) for variant in VARIANTS}}
    return result


def _run_r3(record, data, order_t, entry, stop, sign, risk, valid_until, params):
    """Sabit 3R hedef: ayrı emir çözümü (3R'a dolmadan ulaşılırsa iptal) ve tek bacaklı çıkış."""
    rows, times = data.rows["5m"], data.times["5m"]
    target = entry + sign * R3_MULTIPLE * risk
    status, index = resolve_order(rows, times, order_t, record["direction"], entry, stop, target,
                                  record["poi_distal"], valid_until)
    r3 = {"status": status, "target": target, "rr_tp2": R3_MULTIPLE, "stop_pct": risk / entry * 100.0}
    if status == "FILLED":
        fill_t = rows[index][0]
        r3["fill_t"] = fill_t
        outcome = _outcome(record, rows, index, entry, stop, None, target, "TP2", fill_t, data, params)
        if outcome["exit_reason"] == "TP2":
            outcome["exit_reason"] = "R3"
        r3["outcome"] = outcome
    return r3


def simulate_risk(record, data, params):
    risk = record.get("risk")
    if not risk:
        result = _base(record, "risk")
        result["status"] = "NO_RISK_LEVELS"
        return result
    return _run_order(record, "risk", data, risk["t"], risk["entry"], risk["stop"], risk["tp1"], risk["tp2"],
                      record["first_seen_t"] + params["touch_expiry"], params)


def _zone(record):
    high = max(record["poi_proximal"], record["poi_distal"])
    low = min(record["poi_proximal"], record["poi_distal"])
    return high, low


def simulate_confirmation(record, data, params):
    """POI dokunuşu → LTF teyidi (signals.ltf_status, her 15m kapanışta) → LTF OB limit girişi."""
    rows, times = data.rows["5m"], data.times["5m"]
    direction = record["direction"]
    high, low = _zone(record)
    poi = {"direction": direction, "high": high, "low": low, "distal": record["poi_distal"],
           "proximal": record["poi_proximal"], "eq": record["poi_eq"], "bos_time": record["bos_time"]}
    tf = record["poi_tf"]
    step = replay.fetch_history.INTERVAL_SECONDS[tf]
    result = _base(record, "confirmation")
    sign = _sign(direction)

    # POI'ye ilk dokunuş (BOS mumu kapandıktan sonraki 5m mumlar)
    first_index = bisect.bisect_left(times, record["bos_time"] or record["first_seen_t"])
    touch_index = None
    for index in range(first_index, len(rows)):
        t, o, h, lo_, c, v = rows[index]
        if t >= record["first_seen_t"] + params["touch_expiry"]:
            break
        if lo_ <= high and h >= low:
            touch_index = index
            break
    if touch_index is None:
        result["status"] = "NO_TOUCH"
        return result
    touch_t = rows[touch_index][0]
    tau = ((max(touch_t + FIVE, record["first_seen_t"]) + 899) // 900) * 900
    deadline = max(touch_t, record["first_seen_t"]) + params["confirm_wait"]
    last_close = rows[-1][0] + FIVE
    tp2_seen = record.get("tp2")
    scan_from = bisect.bisect_left(times, record["first_seen_t"])
    while tau <= min(deadline, last_close):
        # teyit gelmeden hedefe ulaşıldıysa iptal
        reached = None
        if tp2_seen is not None:
            hi_idx = bisect.bisect_left(times, tau)
            for index in range(scan_from, hi_idx):
                if ((rows[index][2] >= tp2_seen) if sign > 0 else (rows[index][3] <= tp2_seen)):
                    reached = rows[index][0]
                    break
            scan_from = hi_idx if reached is None else scan_from
        if reached is not None:
            result["status"] = "CANCEL_TP2"
            return result
        # POI hâlâ canlı mı? (taramadaki evaluate_ob_state ile aynı işlev, POI TF mumlarında)
        poi_candles = data.closed(tf, tau, 160)
        bos_index = next((i for i, cnd in enumerate(poi_candles)
                          if record["bos_time"] and cnd["t"] + step == record["bos_time"]), None)
        if bos_index is None:
            result["status"] = "POI_GONE"
            return result
        state = orderblocks.evaluate_ob_state(
            {"direction": direction, "high": high, "low": low, "distal": record["poi_distal"],
             "eq": record["poi_eq"], "bos_index": bos_index}, poi_candles)["state"]
        if state in ("INVALID", "MITIGATED"):
            result["status"] = "POI_" + state
            return result
        status = signals.ltf_status(poi, data.closed("15m", tau), data.closed("5m", tau),
                                    record.get("stack_count", 1), None, htf_state=state)
        if status["status"] == "INVALIDATED":
            result["status"] = "CANCEL_INVALID"
            return result
        if status["ltf_ob"]:
            levels = signals.levels(
                poi, direction=direction, market="crypto", symbol=record["symbol"],
                atr_value=indicators.atr(poi_candles, config.ATR_PERIOD),
                current_price=data.closed("5m", tau, 1)[-1]["c"],
                entry_type="double_confirmation" if status["status"] == "ENTRY2_READY" else "confirmation",
                irl_levels=record["ctx"]["irl"], pd_levels=record["ctx"]["pd"], pw_levels=record["ctx"]["pw"],
                targeted_level=record["ctx"]["targeted"], ltf_ob=status["ltf_ob"])
            # Min stop hipotezleri: (a) giriş × %0.5, (b) 1h ATR(14) — teyit anına kadar KAPANMIŞ 1h mumlarla
            atr_1h = indicators.atr(data.closed("1h", tau, config.ATR_PERIOD + 1), config.ATR_PERIOD)
            min_stops = {"minstop_pct": MIN_STOP_PCT * levels["entry"], "minstop_atr": atr_1h or None}
            return _run_order(record, "confirmation", data, tau, levels["entry"], levels["stop"],
                              levels["tp1"], levels["tp2"], tau + params["confirm_fill"], params,
                              {"confirm_t": tau, "confirm_status": status["status"], "ltf_tf": status["ltf_tf"],
                               "atr_1h": atr_1h}, min_stops=min_stops)
        tau += 900
    result["status"] = "PENDING_END" if last_close < deadline else "NO_CONFIRM"
    return result


def simulate_setup(record, data, params=None):
    """Bir setup için risk ve confirmation modu sonuçları (liste)."""
    params = params or _params()
    return [simulate_risk(record, data, params), simulate_confirmation(record, data, params)]


# ------------------------------------------------------------------ çok süreçli
def simulate_worker(job):
    data = replay.SymbolData.load(job["symbol"], job["data_dir"])
    trades = []
    for record in job["setups"]:
        trades.extend(simulate_setup(record, data))
    return job["symbol"], trades


def simulate_all(setups, symbols, data_dir, workers=1, print_fn=print):
    """Setup listesini sembol bazında simüle eder; çıktı (first_seen_t, sembol, mod) sırasıyla deterministiktir."""
    by_symbol = {symbol: [r for r in setups if r["symbol"] == symbol] for symbol in symbols}
    jobs = [{"symbol": symbol, "data_dir": data_dir, "setups": by_symbol[symbol]}
            for symbol in symbols if by_symbol[symbol]]
    results = {}
    if workers > 1 and len(jobs) > 1:
        import multiprocessing
        context = multiprocessing.get_context("spawn")
        with context.Pool(processes=min(workers, len(jobs))) as pool:
            for symbol, trades in pool.imap(simulate_worker, jobs):
                results[symbol] = trades
                print_fn("simülasyon {} bitti ({} kayıt)".format(symbol, len(trades)))
    else:
        for job in jobs:
            symbol, trades = simulate_worker(job)
            results[symbol] = trades
            print_fn("simülasyon {} bitti ({} kayıt)".format(symbol, len(trades)))
    merged = [trade for symbol in symbols for trade in results.get(symbol, [])]
    merged.sort(key=lambda t: (t["first_seen_t"], t["symbol"], MODES.index(t["mode"]), t["key"]))
    return merged
