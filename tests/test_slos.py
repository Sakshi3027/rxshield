"""The SLO check must pass a healthy run and flag slow endpoints, failures, and missing endpoints."""
import csv

from loadtest.slos import SLOS_P95_MS, check

FIELDS = ["Type", "Name", "Request Count", "Failure Count", "95%"]


def write_stats(path, p95_overrides=None, failures=0, drop=None):
    rows = [{"Type": "GET", "Name": name, "Request Count": 100, "Failure Count": 0,
             "95%": (p95_overrides or {}).get(name, target / 2)}
            for name, target in SLOS_P95_MS.items() if name != drop]
    rows.append({"Type": "", "Name": "Aggregated", "Request Count": 500, "Failure Count": failures, "95%": 300})
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def test_healthy_run_meets_all_slos(tmp_path):
    assert check(write_stats(tmp_path / "ok.csv")) == []


def test_slow_endpoint_is_flagged(tmp_path):
    problems = check(write_stats(tmp_path / "slow.csv", p95_overrides={"/simulations/whatif": 2500}))
    assert problems == ["/simulations/whatif: p95 2500 ms exceeds 1500 ms"]


def test_high_failure_rate_is_flagged(tmp_path):
    assert any("failure rate" in p for p in check(write_stats(tmp_path / "fail.csv", failures=10)))


def test_missing_endpoint_is_flagged(tmp_path):
    assert check(write_stats(tmp_path / "gap.csv", drop="/me")) == ["/me: not measured in this run"]
