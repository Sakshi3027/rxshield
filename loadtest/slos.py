"""Service level objectives for RxShield, checked against a Locust results CSV.

Targets are p95 latencies set at roughly 1.5 to 2 times the local baseline, leaving headroom for the
deployed environment while still catching real regressions. Usage: python -m loadtest.slos <stats.csv>
"""
import csv
import sys

SLOS_P95_MS = {
    "/ask [cached]": 800,
    "/me": 500,
    "/memos/pending": 500,
    "/simulations/whatif": 1500,
    "/auth/login": 800,
}
MAX_FAILURE_RATE = 0.005


def check(stats_csv: str) -> list[str]:
    with open(stats_csv, newline="") as handle:
        rows = list(csv.DictReader(handle))
    problems = []
    for row in rows:
        name = row["Name"]
        if name == "Aggregated":
            total, failed = int(row["Request Count"]), int(row["Failure Count"])
            if total and failed / total > MAX_FAILURE_RATE:
                problems.append(f"failure rate {failed / total:.2%} exceeds {MAX_FAILURE_RATE:.1%}")
        elif name in SLOS_P95_MS and float(row["95%"]) > SLOS_P95_MS[name]:
            problems.append(f"{name}: p95 {float(row['95%']):.0f} ms exceeds {SLOS_P95_MS[name]} ms")
    measured = {row["Name"] for row in rows}
    problems += [f"{name}: not measured in this run" for name in SLOS_P95_MS if name not in measured]
    return problems


def main(stats_csv: str) -> None:
    problems = check(stats_csv)
    print("\n".join(problems) if problems else "All SLOs met.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main(sys.argv[1])
