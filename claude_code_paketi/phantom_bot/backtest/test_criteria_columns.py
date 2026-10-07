"""Kriter 0/1 sütunları: replay kaydı → simülasyon → işlem CSV."""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report_bt as rb  # noqa: E402
import replay  # noqa: E402
import test_report_bt as T  # noqa: E402
import test_simulate as S  # noqa: E402


def main():
    flags = rb.criteria_flags([{"criterion": "htf_alignment", "points": 20}, {"criterion": "stack_2tf", "points": 12},
                               {"criterion": "fvg", "points": 6}, {"criterion": "v_reversal_penalty", "points": -10}])
    assert flags["crit_htf_alignment"] == 1 and flags["crit_stack_2plus"] == 1 and flags["crit_stack_3tf"] == 0
    assert flags["crit_fvg"] == 1 and flags["crit_v_reversal_penalty"] == 1 and flags["crit_inducement"] == 0
    assert flags == rb.criteria_flags(list(reversed([{"criterion": "htf_alignment"}, {"criterion": "stack_2tf"},
                                                       {"criterion": "fvg"}, {"criterion": "v_reversal_penalty"}])))
    assert rb.criteria_flags(None)["crit_stack_2plus"] == 0 and rb.criteria_flags([{"criterion": "stack_3tf"}])["crit_stack_2plus"] == 1
    assert len(rb.REPORT_CRITERIA) == 12 and "preferred_session" not in rb.REPORT_CRITERIA

    # Replay kaydı score_breakdown taşır ve sürüm numarası pencere anahtarında yer alır.
    series, data, record = S.confirmation_fixture()
    assert isinstance(record["score_breakdown"], list) and record["score_breakdown"]
    assert {"criterion", "points"} <= set(record["score_breakdown"][0])
    assert replay.REPLAY_VERSION >= 2

    # Simülasyon sonucu → düzleştirilmiş satır → CSV sütunları
    trades = S.simulate.simulate_setup(record, data)
    assert all(t["score_breakdown"] == record["score_breakdown"] for t in trades)
    rows = rb.flatten(trades)
    expected = rb.criteria_flags(record["score_breakdown"])
    assert rows and all(all(row[key] == value for key, value in expected.items()) for row in rows)
    out = tempfile.mkdtemp(prefix="bt_crit_")
    paths = rb.write_reports(trades, T.WINDOW, out, stamp="x")
    with open(paths["trades"], encoding="utf-8-sig") as handle:
        written = list(csv.DictReader(handle))
    assert written and all(column in written[0] for column in rb.CRITERIA_COLUMNS)
    assert all(int(written[0][key]) == value for key, value in expected.items())
    print("Kriter 0/1 sütunları (replay → simülasyon → CSV): GEÇTİ")
    print("test_criteria_columns: OK")


if __name__ == "__main__":
    main()
