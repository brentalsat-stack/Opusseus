from datetime import datetime, timezone

import pytest

from photon.data import ensure_utc, local_to_utc, to_istanbul, to_london


def test_naive_rejected():
    with pytest.raises(ValueError):
        ensure_utc(datetime(2021, 9, 1, 7, 0))


def test_london_dst_follows_iana():
    summer = datetime(2021, 9, 1, 6, 0, tzinfo=timezone.utc)   # BST = UTC+1
    winter = datetime(2021, 12, 1, 7, 0, tzinfo=timezone.utc)  # GMT
    assert to_london(summer).hour == 7 and to_london(winter).hour == 7


def test_istanbul_fixed_utc_plus_3_and_session_mapping():
    # 07:00 London: yaz 09:00 İstanbul, kış 10:00 İstanbul (DECISIONS §6)
    s = local_to_utc(datetime(2021, 9, 1, 7, 0), "Europe/London")
    w = local_to_utc(datetime(2021, 12, 1, 7, 0), "Europe/London")
    assert to_istanbul(s).hour == 9 and to_istanbul(w).hour == 10


def test_nonexistent_local_time_rejected():
    with pytest.raises(ValueError):
        local_to_utc(datetime(2021, 3, 28, 1, 30), "Europe/London")


def test_ambiguous_time_uses_fold():
    a = local_to_utc(datetime(2021, 10, 31, 1, 30), "Europe/London", fold=0)
    b = local_to_utc(datetime(2021, 10, 31, 1, 30), "Europe/London", fold=1)
    assert (b - a).total_seconds() == 3600


def test_result_is_utc():
    assert local_to_utc(datetime(2021, 9, 1, 7, 0), "Europe/London").utcoffset().total_seconds() == 0
