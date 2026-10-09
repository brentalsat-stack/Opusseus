"""EN-R006 (T-EN-02/03/04), pro/karşı trend sınıflaması, PD-R001, haber uyarısı."""
import json
from datetime import datetime, timezone
from decimal import Decimal as D

import pytest

from photon.config import load_config
from photon.signals.news import NewsCalendar, NewsStatus, fetch_forexfactory, parse_forexfactory
from photon.strategy.permission import TrendClass, check_permission, classify_trend
from photon.structure import Seed, StructureEngine, StructureParams, Trend
from photon.structure import pd as PD
from photon.data import Timeframe

B, S, U = Trend.BULL, Trend.BEAR, Trend.UNDEFINED
UTC = timezone.utc


def perm(t4, t15, d=B, htf=True, p4=False, choch=False):
    return check_permission(t4, t15, d, price_in_htf_poi=htf, price_in_4h_poi=p4, m15_choch_toward_dir=choch)


def test_t_en_02_pro_counter_only_m15_poi_denied():
    r = perm(B, S, htf=True, p4=False)
    assert not r.allowed and r.row == "PRO/COUNTER" and r.rule == "EN-R006"


def test_t_en_03_pro_counter_after_4h_poi_mitigation_allowed():
    assert perm(B, S, htf=True, p4=True).allowed


def test_t_en_04_counter_counter_denied_until_m15_choch():
    assert not perm(S, S, htf=True, p4=True).allowed
    r = perm(S, S, htf=True, choch=True)                    # M15 CHoCH → COUNTER/PRO satırı
    assert r.allowed and r.row.startswith("COUNTER/COUNTER→CHoCH")
    assert not perm(S, S, htf=False, choch=True).allowed    # POI şartı hâlâ var


def test_pro_pro_and_counter_pro_require_htf_poi():
    assert perm(B, B).allowed and not perm(B, B, htf=False).allowed
    assert perm(S, B).allowed and not perm(S, B, htf=False).allowed         # 4H karşı, M15 yönde
    assert perm(B, S, htf=True, choch=True).allowed                          # PRO/COUNTER → CHoCH → PRO/PRO
    assert not perm(B, S, htf=False, choch=True).allowed                     # POI şartı CHoCH sonrası da geçerli


def test_short_direction_mirror_and_undefined():
    assert perm(S, S, d=S).allowed and not perm(B, B, d=S, p4=False).allowed
    r = perm(U, B)
    assert not r.allowed and "TREND_UNDEFINED" in r.reason
    with pytest.raises(ValueError):
        perm(B, B, d=U)


def test_trend_classification_decisions_s5():
    assert classify_trend(B, B, B) is TrendClass.PRO
    assert classify_trend(S, B, B) is TrendClass.COUNTER_HTF and classify_trend(S, S, B) is TrendClass.COUNTER_HTF
    assert classify_trend(B, S, B) is TrendClass.MIXED                       # Q-P6
    with pytest.raises(ValueError):
        classify_trend(U, B, B)


# ---------------- PD-R001 ----------------
def test_pd_eq_and_classification():
    assert PD.eq(D("1.1000"), D("1.1040")) == D("1.1020")                    # FM-08
    assert PD.classify(D("1.10199"), D("1.1000"), D("1.1040")) is PD.PD.DISCOUNT
    assert PD.classify(D("1.10201"), D("1.1000"), D("1.1040")) is PD.PD.PREMIUM
    assert PD.classify(D("1.1020"), D("1.1000"), D("1.1040")) is PD.PD.EQ
    with pytest.raises(ValueError):
        PD.eq(D("1.1"), D("1.1"))


def test_pd_alignment():
    assert PD.aligned(B, PD.PD.DISCOUNT) and not PD.aligned(B, PD.PD.PREMIUM) and PD.aligned(S, PD.PD.PREMIUM)
    assert PD.aligned(B, PD.PD.EQ) is False and PD.aligned(B, None) is None


def test_pd_from_market_state_confirmed_range_only():
    from photon.tests.test_structure import UP, UP_SEED, bar, bars, px, params, engine
    e = engine(bars(UP), UP_SEED)
    st = e.state()
    assert PD.swing_range(st) == (px(0), px(40))
    assert PD.classify_state(st, px(10)) is PD.PD.DISCOUNT and PD.classify_state(st, px(30)) is PD.PD.PREMIUM
    e.update(bar(6, 45, 30, c=42))                    # BOS → yeni uç onaysız → P/D bilinmez (Q-S06)
    assert PD.swing_range(e.state()) is None and PD.classify_state(e.state(), px(10)) is None
    cold = StructureEngine(Timeframe.H4, params())
    assert PD.swing_range(cold.state()) is None


# ---------------- haber ----------------
FF = [
    {"title": "Non-Farm Employment Change", "country": "USD", "date": "2021-09-03T08:30:00-04:00", "impact": "High", "forecast": "", "previous": ""},
    {"title": "German Factory Orders", "country": "EUR", "date": "2021-09-06T02:00:00-04:00", "impact": "Low", "forecast": "", "previous": ""},
    {"title": "ECB Press Conference", "country": "EUR", "date": "2021-09-09T08:30:00-04:00", "impact": "High", "forecast": "", "previous": ""},
    {"title": "GBP High", "country": "GBP", "date": "2021-09-07T04:30:00-04:00", "impact": "High", "forecast": "", "previous": ""},
    {"title": "Bank Holiday", "country": "USD", "date": "2021-09-06T00:00:00-04:00", "impact": "Holiday", "forecast": "", "previous": ""},
    {"title": "OPEC", "country": "All", "date": "2021-09-08T05:15:00-04:00", "impact": "High", "forecast": "", "previous": ""},
]


@pytest.fixture
def cal():
    return NewsCalendar.from_config(load_config(), parse_forexfactory(json.dumps(FF)))


def test_parse_converts_to_utc():
    ev = parse_forexfactory(json.dumps(FF))
    assert ev[0].time == datetime(2021, 9, 3, 12, 30, tzinfo=UTC) and ev[0].currency == "USD"


def test_all_signals_of_the_day_get_warning(cal):
    n1 = cal.note(datetime(2021, 9, 3, 7, 0, tzinfo=UTC))        # NFP günü, haberden ÖNCE
    n2 = cal.note(datetime(2021, 9, 3, 14, 0, tzinfo=UTC))       # haberden SONRA
    assert n1.status is n2.status is NewsStatus.WARN
    assert "Non-Farm" in n1.text() and "15:30" in n1.text()      # İstanbul saati (UTC+3)


def test_only_high_impact_eur_usd_count(cal):
    assert cal.note(datetime(2021, 9, 6, 10, 0, tzinfo=UTC)).status is NewsStatus.CLEAR    # Low + Holiday
    assert cal.note(datetime(2021, 9, 7, 10, 0, tzinfo=UTC)).status is NewsStatus.CLEAR    # GBP High
    assert cal.note(datetime(2021, 9, 8, 10, 0, tzinfo=UTC)).status is NewsStatus.CLEAR    # country=All
    assert cal.note(datetime(2021, 9, 9, 10, 0, tzinfo=UTC)).status is NewsStatus.WARN


def test_outside_calendar_coverage_is_unknown_not_clear(cal):
    n = cal.note(datetime(2021, 8, 1, 10, 0, tzinfo=UTC))
    assert n.status is NewsStatus.UNKNOWN and "bilinmiyor" in n.text()


def test_day_boundary_is_istanbul_midnight(cal):
    # Haber 12:30 UTC (15:30 İst.). 2021-09-03 20:59 UTC = 23:59 İst. aynı gün; 21:00 UTC = ertesi gün
    assert cal.note(datetime(2021, 9, 3, 20, 59, tzinfo=UTC)).status is NewsStatus.WARN
    assert cal.note(datetime(2021, 9, 3, 21, 0, tzinfo=UTC)).status is NewsStatus.CLEAR


def test_note_never_blocks_signal_text_is_string(cal):
    assert isinstance(cal.note(datetime(2021, 9, 9, 10, 0, tzinfo=UTC)).text(), str)


def test_fetch_uses_http_get_and_url():
    seen = []
    def get(url, headers):
        seen.append(url)
        return 200, json.dumps(FF).encode(), {}
    ev = fetch_forexfactory(load_config().get("news_filter.feed_url"), get)
    assert len(ev) == 6 and seen[0].startswith("https://")
    with pytest.raises(RuntimeError):
        fetch_forexfactory("u", lambda u, h: (404, b"", {}))


def test_q_p1_m15_choch_only_counts_after_4h_poi_mitigation():
    from photon.strategy.permission import m15_choch_after_mitigation
    from photon.structure.models import EventType, StructureEvent
    mit = datetime(2021, 9, 1, 10, 0, tzinfo=UTC)

    def e(minute, d=B, warm=False, typ=EventType.CHOCH):
        return StructureEvent(Timeframe.M15, typ, d, D("1.1"), 5, datetime(2021, 9, 1, 10, minute, tzinfo=UTC), False, warmup=warm)
    assert not m15_choch_after_mitigation([e(0)], mit, B)                    # aynı mum → sayılmaz
    assert not m15_choch_after_mitigation([StructureEvent(Timeframe.M15, EventType.CHOCH, B, D("1.1"), 1,
                                                          datetime(2021, 9, 1, 9, 45, tzinfo=UTC), False)], mit, B)  # mitigasyondan önce
    assert m15_choch_after_mitigation([e(15)], mit, B)
    assert not m15_choch_after_mitigation([e(15, d=S)], mit, B)              # ters yönlü CHoCH
    assert not m15_choch_after_mitigation([e(15, warm=True)], mit, B)        # warm-up
    assert not m15_choch_after_mitigation([e(15, typ=EventType.BOS)], mit, B)


def test_q_p6_mixed_management_decision_in_config():
    assert load_config().get("target_allocation.mixed") == {"same_as": "pro_trend"}
    load_config().require("management")
