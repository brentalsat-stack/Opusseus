"""Sinyal çıktısı (Aşama 6): ekran + log dosyası (DECISIONS §1 bildirim). Emri kullanıcı girer — otomatik emir YOK.
İçerik: zaman (İstanbul saati), parite, yön, giriş, stop, hedefler (+ hacim), önerilen lot (+ birim), POI puanı + kriter dökümü,
kural ID'leri, 4H/M15 trend, seans, ForexFactory haber uyarısı."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from ..data.tz import ISTANBUL, ensure_utc
from ..execution.management import RISK_REMOVAL
from ..risk.stops import Side
from ..strategy.entry_model import OrderIntent, SignalEvent
from ..strategy.state_machine import Setup

log = logging.getLogger("photon.signal")


def _p(x) -> str:
    return f"{x:f}"


def _n(x) -> str:
    """Decimal'i sondaki sıfırlar olmadan yaz (1.00 → 1, 16.0 → 16)."""
    return f"{x.normalize():f}"


def format_signal(it: OrderIntent, display_tz: ZoneInfo = ISTANBUL) -> str:
    t = ensure_utc(it.time).astimezone(display_tz)
    pip = abs(it.entry - it.stop)
    lines = [
        f"═══ PHOTON SİNYAL ═══  {t:%Y-%m-%d %H:%M} ({display_tz.key})",
        f"Parite: {it.pair}   Yön: {'LONG (alış)' if it.side is Side.LONG else 'SHORT (satış)'}   Emir: {it.type} (emri siz girin)",
        f"Giriş: {_p(it.entry)}   Stop: {_p(it.stop)}  ({it.pip_risk:f} pip)",
        f"Lot: {it.lots:.2f} ({it.units:,.0f} birim)   Risk: %{_n(it.risk_pct * 100)} = {it.risk_amount:.2f}",
        "Hedefler:",
    ]
    long = it.side is Side.LONG
    for i, leg in enumerate(it.plan.legs, 1):
        r = ((leg.price - it.entry) if long else (it.entry - leg.price)) / pip if pip else 0
        extra = " → risk kaldırılır, stop yerinde" if leg.name == RISK_REMOVAL else \
            (f" [tutma onayı: {leg.hold_requires}; yoksa M15 hedefinde kapanır]" if leg.hold_requires else "")
        lines.append(f"  {i}) {leg.label or leg.name}: {_p(leg.price)}  %{_n(leg.pct)}  ({r:.1f}R){extra}")
    lines.append("İptal: " + (f"dolmadan {_p(it.cancel_if_reaches)} seviyesine ulaşılırsa" if it.cancel_if_reaches is not None
                              else "ilk hedef tanımlı değil"))
    lines += [
        f"POI: {it.poi_tf.value} {it.poi_id} | giriş zonu: {it.entry_zone_kind} {it.entry_zone_id}",
        f"POI puanı: {_n(it.poi_score)}/{_n(it.poi_max_score)} — {it.score_breakdown}",
    ]
    if it.shares_event_with:
        lines.append(f"Uyarı: aynı yapı olayına bağlı başka zonlar da var (çift sayım): {', '.join(it.shares_event_with)}")
    lines += [
        f"Trend: 4H {it.h4_trend} / M15 {it.m15_trend} ({it.trend_class})",
        f"Seans: {it.session or 'seans dışı'}",
        f"Haber: {it.news or 'uyarı yok'}",
        "Kurallar: " + ", ".join(it.rules),
    ]
    if it.plan.notes:
        lines.append("Plan notu: " + "; ".join(it.plan.notes))
    return "\n".join(lines)


def format_cancel(setup: Setup, time: datetime, reason: str, display_tz: ZoneInfo = ISTANBUL) -> str:
    t = ensure_utc(time).astimezone(display_tz)
    return f"═══ PHOTON İPTAL ═══  {t:%Y-%m-%d %H:%M} ({display_tz.key}) — {setup.id}: {reason} (bekleyen limit emri iptal edin)"


class SignalPublisher:
    """`notifications` config'i: SCREEN → printer, LOG_FILE → 'photon.signal' logger'ı (logging.file'a yazar)."""

    def __init__(self, channels: Sequence[str], printer: Callable[[str], None] = print, display_tz: ZoneInfo = ISTANBUL):
        unknown = set(channels) - {"SCREEN", "LOG_FILE"}
        if unknown:
            raise ValueError(f"bilinmeyen bildirim kanalı: {sorted(unknown)}")
        self.channels, self.printer, self.tz = set(channels), printer, display_tz

    @classmethod
    def from_config(cls, cfg, printer: Callable[[str], None] = print) -> "SignalPublisher":
        cfg.require("signals")
        from zoneinfo import ZoneInfo as Z
        return cls(cfg.get("notifications"), printer, Z(cfg.get("timezones.display")))

    def _emit(self, text: str) -> None:
        if "SCREEN" in self.channels:
            self.printer(text)
        if "LOG_FILE" in self.channels:
            log.info("\n%s", text)

    def publish(self, ev: SignalEvent) -> str | None:
        """SIGNAL ve CANCELLED ekrana + log'a; REJECTED yalnızca log'a (DEBUG değil INFO satırı). Döner: yayımlanan metin."""
        if ev.kind == "SIGNAL":
            text = format_signal(ev.intent, self.tz)
        elif ev.kind == "CANCELLED":
            text = format_cancel(ev.setup, ev.time, ev.reason, self.tz)
        else:
            if "LOG_FILE" in self.channels:
                log.info("RET %s %s: %s", ev.time.isoformat(), ev.setup.id, ev.reason)
            return None
        self._emit(text)
        return text
