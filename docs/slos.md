# RxShield service level objectives

Targets are p95 latencies, set at roughly 1.5 to 2 times the measured local baseline. That leaves
headroom for the deployed environment while still catching real regressions.

## Targets

| Path | Measured p95 | SLO p95 | How it is measured |
|---|---|---|---|
| Cached answer (`POST /ask`, cache hit) | 452 ms | 800 ms | Locust, `loadtest/slos.py` |
| Identity (`GET /me`) | 330 ms | 500 ms | Locust, `loadtest/slos.py` |
| Pending memos (`GET /memos/pending`) | 330 ms | 500 ms | Locust, `loadtest/slos.py` |
| Outage simulation (`POST /simulations/whatif`) | 960 ms | 1,500 ms | Locust, `loadtest/slos.py` |
| Login (`POST /auth/login`, bcrypt by design) | 520 ms | 800 ms | Locust, `loadtest/slos.py` |
| New answer (`POST /ask`, cache miss, calls the LLM) | 10,071 ms | 15,000 ms | Trace spans in `ops.spans` |
| Availability (all requests not 5xx) | 100% | 99.5% | Locust failure rate, `loadtest/slos.py` |

## Baseline run

- Locust, 20 simulated users across 12 users in 4 hospitals, 3 minutes, one API worker on a laptop.
- 1,426 requests, 0 failures, 8.7 requests per second.
- Results: `loadtest/results/baseline_stats.csv`. Check: `python -m loadtest.slos loadtest/results/baseline_stats.csv`.

## Findings

- **The semantic cache is about 15x faster at the median** (275 ms vs 4,017 ms) and needs no LLM tokens.
- **Cache hits do not count against the answer quota.** The run sent about 60 cached answers per minute per
  hospital against a limit of 30, with no rate-limit responses. Only new LLM answers use the quota.
- **Every authenticated request costs about 165 ms at minimum**, mostly the database round trip and
  per-request row-level security setup.

## Caveats

- Measured locally with one worker. Deployed numbers will differ; rerun the load test after deploying.
- The cache-miss target is based on 21 traced requests and mostly reflects the LLM provider's latency.
- Load tests deliberately avoid new questions so they do not spend the LLM budget.
