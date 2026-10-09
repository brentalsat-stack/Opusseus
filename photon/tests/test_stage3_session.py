"""SS-R001, SS-R002, T-SS-01/02, DST geçişleri, İstanbul gösterimi."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from photon.config import ConfigError, load_config
from photon.risk.session import SessionClock

UTC = timezone.utc
LON = ZoneInfo("Europe/London")


@pytest.fixture
def clock():
    return SessionClock.from_config(load_config())


def lon(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=LON).astimezone(UTC)


def test_t_ss_01_10_15_london_is_outside(clock):
    d = clock.may_open(lon(2021, 9, 1, 10, 15))
    assert not d.allowed and d.reason == "OUT_OF_SESSION" and d.rule == "SS-R001"


@pytest.mark.parametrize("h,mi,inside", [(6, 59, False), (7, 0, True), (9, 59, True), (10, 0, False),
                                          (11, 59, False), (12, 0, True), (14, 59, True), (15, 0, False)])
def test_window_edges_start_inclusive_end_exclusive(clock, h, mi, inside):
    assert clock.in_session(lon(2021, 9, 1, h, mi)) is inside        # yaz (BST)
    assert clock.in_session(lon(2021, 12, 1, h, mi)) is inside       # kış (GMT)


def test_dst_transition_days_follow_london_wall_clock(clock):
    # 2021-03-28 Londra yaz saatine geçti (01:00 UTC); 07:00 BST = 06:00 UTC
    assert clock.in_session(datetime(2021, 3, 28, 6, 0, tzinfo=UTC))
    assert not clock.in_session(datetime(2021, 3, 28, 5, 59, tzinfo=UTC))
    # 2021-10-31 kış saatine geçti: 07:00 GMT = 07:00 UTC
    assert clock.in_session(datetime(2021, 10, 31, 7, 0, tzinfo=UTC))
    assert not clock.in_session(datetime(2021, 10, 31, 6, 59, tzinfo=UTC))


def test_t_ss_02_blackout_21_30_gmt(clock):
    d = clock.may_open(datetime(2021, 12, 1, 21, 30, tzinfo=UTC))
    assert not d.allowed and d.reason == "BLACKOUT" and d.rule == "SS-R002"
    # Yaz: 21:30 UTC = 22:30 Londra; yasak UTC sabit olduğundan yine yasak
    assert clock.in_blackout(datetime(2021, 9, 1, 21, 30, tzinfo=UTC))
    assert clock.in_blackout(datetime(2021, 9, 1, 21, 0, tzinfo=UTC)) and not clock.in_blackout(datetime(2021, 9, 1, 23, 0, tzinfo=UTC))
    assert not clock.in_blackout(datetime(2021, 9, 1, 20, 59, tzinfo=UTC))
    # Yasak GMT'ye sabit, Londra yerel saatine DEĞİL: yazın 22:30 UTC = 23:30 Londra'da da yasak, 23:00 UTC'de değil
    assert clock.in_blackout(datetime(2021, 9, 1, 22, 59, tzinfo=UTC))


def test_istanbul_display_windows_summer_and_winter(clock):
    summer = clock.windows_display(date(2021, 9, 1))
    assert [(a.hour, b.hour) for a, b in summer] == [(9, 12), (14, 17)]        # DECISIONS §6: yaz 09–12 / 14–17
    winter = clock.windows_display(date(2021, 12, 1))
    assert [(a.hour, b.hour) for a, b in winter] == [(10, 13), (15, 18)]       # kış 10–13 / 15–18
    assert summer[0][0].utcoffset().total_seconds() == 3 * 3600


def test_session_without_blackout_works_independently():
    c = SessionClock.from_config(load_config(), with_blackout=False)
    assert c.may_open(lon(2021, 9, 1, 8)).allowed
    with pytest.raises(RuntimeError):
        c.in_blackout(lon(2021, 9, 1, 8))


def test_blackout_gate_failfast_when_tz_required(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(open("config.yaml", encoding="utf-8").read().replace("blackout: {tz: UTC", "blackout: {tz: REQUIRED"), encoding="utf-8")
    cfg = load_config(p)
    SessionClock.from_config(cfg, with_blackout=False)          # session bağımsız çalışır
    with pytest.raises(ConfigError, match="blackout.tz"):
        SessionClock.from_config(cfg)


def test_naive_rejected(clock):
    with pytest.raises(ValueError):
        clock.in_session(datetime(2021, 9, 1, 8))
