from datetime import datetime, timedelta

from photon.data import IssueKind, Timeframe, check_series
from photon.tests.helpers import UTC, qc


def series(times):
    return [qc(t) for t in times]


T0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)


def test_clean_series_ok():
    rep = check_series(series([T0 + timedelta(minutes=i) for i in range(10)]), Timeframe.M1)
    assert rep.ok and rep.n_candles == 10 and not rep.issues


def test_missing_candle_reported_not_fixed():
    ts = [T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=5)]
    rep = check_series(series(ts), Timeframe.M1)
    (i,) = rep.issues                       # T-DATA-01
    assert i.kind is IssueKind.MISSING and i.missing_candles == 3 and i.start == T0 + timedelta(minutes=2)
    assert not rep.ok


def test_duplicate_and_out_of_order():
    ts = [T0, T0, T0 + timedelta(minutes=2), T0 + timedelta(minutes=1)]
    rep = check_series(series(ts), Timeframe.M1)
    assert rep.count(IssueKind.DUPLICATE) == 1 and rep.count(IssueKind.OUT_OF_ORDER) == 1
    assert rep.count(IssueKind.MISSING) == 1      # T0 → T0+2dk arası 1 dakika eksik


def test_weekend_gap_not_blocking():
    fri = datetime(2021, 9, 3, 20, 59, tzinfo=UTC)
    sun = datetime(2021, 9, 5, 21, 0, tzinfo=UTC)
    rep = check_series(series([fri, sun]), Timeframe.M1)
    assert rep.count(IssueKind.WEEKEND_GAP) == 1 and rep.ok


def test_midweek_gap_over_a_day_is_missing():
    rep = check_series(series([T0, T0 + timedelta(days=1, hours=2)]), Timeframe.M1)
    assert rep.count(IssueKind.MISSING) == 1


def test_friday_gap_not_reaching_saturday_is_missing():
    fri = datetime(2021, 9, 3, 10, 0, tzinfo=UTC)
    rep = check_series(series([fri, fri + timedelta(hours=3)]), Timeframe.M1)
    assert rep.count(IssueKind.MISSING) == 1


def test_wrong_tf_raises():
    import pytest
    with pytest.raises(ValueError):
        check_series(series([T0]), Timeframe.M15)
