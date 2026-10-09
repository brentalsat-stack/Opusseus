from datetime import datetime, timedelta
from decimal import Decimal as D

from photon.data import CandleStore, Timeframe
from photon.tests.helpers import UTC, qc

T0 = datetime(2021, 9, 1, 8, 0, tzinfo=UTC)


def test_roundtrip_exact_decimal_and_range():
    s = CandleStore(":memory:")
    cs = [qc(T0 + timedelta(minutes=i), n_ticks=i) for i in range(5)]
    assert s.put_candles("X", cs) == 5
    got = list(s.get_candles("X", "EURUSD", Timeframe.M1, T0 + timedelta(minutes=1), T0 + timedelta(minutes=4)))
    assert [g.open_time for g in got] == [c.open_time for c in cs[1:4]]
    assert got[0] == cs[1] and got[0].bid.open == D("1.1000")
    assert list(s.get_candles("OTHER", "EURUSD", Timeframe.M1, T0, T0 + timedelta(hours=1))) == []


def test_put_is_idempotent_and_chunks():
    s = CandleStore(":memory:")
    s.put_candles("X", [qc(T0)])
    s.put_candles("X", [qc(T0)])
    assert len(list(s.get_candles("X", "EURUSD", Timeframe.M1, T0, T0 + timedelta(hours=1)))) == 1
    assert s.chunk_status("X", "EURUSD", "k") is None
    s.mark_chunk("X", "EURUSD", "k", "EMPTY")
    assert s.chunk_status("X", "EURUSD", "k") == "EMPTY"


def test_file_db_created(tmp_path):
    s = CandleStore(tmp_path / "a" / "b.sqlite")
    s.close()
    assert (tmp_path / "a" / "b.sqlite").exists()
