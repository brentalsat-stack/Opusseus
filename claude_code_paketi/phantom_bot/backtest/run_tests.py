"""backtest/ testlerinin hepsini sırayla çalıştırır (ağ gerekmez). Kullanım: python backtest\\run_tests.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ["test_fetch_history.py", "test_replay.py", "test_simulate.py", "test_bt_stats.py", "test_report_bt.py", "test_criteria_columns.py", "test_analysis_bt.py",
         "test_run_backtest.py"]


def main():
    failed = []
    for name in TESTS:
        print("== {}".format(name))
        code = subprocess.call([sys.executable, os.path.join(HERE, name)])
        if code != 0:
            failed.append(name)
    print("BAŞARISIZ: {}".format(", ".join(failed)) if failed else "Tüm backtest testleri geçti.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
