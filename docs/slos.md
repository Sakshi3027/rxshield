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

- The cache-miss target is based on 21 traced requests and mostly reflects the LLM provider's latency.
- Load tests deliberately avoid new questions so they do not spend the LLM budget.

## Deployed run (Render free tier: 0.15 vCPU, 512 MB)

Same Locust profile against the deployed API in Render's Virginia region, next to Supabase (us-east-1).
Two runs: 2 users for 2 minutes (what one person experiences) and 20 users for 3 minutes (capacity).
Zero failures in both.

| Path | Laptop p95 | Render p95, 2 users | Render p95, 20 users |
|---|---|---|---|
| Pending memos (`GET /memos/pending`) | 330 ms | 240 ms (median 59 ms) | 16,000 ms |
| Identity (`GET /me`) | 330 ms | 810 ms (median 63 ms) | 13,000 ms |
| Cached answer (`POST /ask`, cache hit) | 452 ms | 2,100 ms | 23,000 ms |
| Outage simulation (`POST /simulations/whatif`) | 960 ms | 4,200 ms | 126,000 ms |
| Login (`POST /auth/login`) | 520 ms | 4,100 ms | 39,000 ms |
| Throughput | 8.7 req/s | 0.65 req/s | 0.78 req/s |

Results: `loadtest/results/prod_light_stats.csv` and `loadtest/results/prod_stats.csv`.

### Findings

- **Database-bound requests are faster deployed than on the laptop.** Median `/me` is 63 ms on Render
  against a floor of about 165 ms locally, because the API runs in the same region as the database.
- **CPU-bound requests are 4 to 8 times slower.** A cached answer embeds the question before the lookup,
  login runs bcrypt, and the outage simulation is computation heavy. Each takes seconds on 0.15 vCPU.
- **Capacity is about 1 request per second.** Throughput barely rises from 2 to 20 users, so the CPU is
  saturated and extra users wait in a queue (about 12 requests in flight at 0.78 req/s and 15.7 s average).
- **The free tier meets the availability SLO but not the latency SLOs on CPU-bound paths.** The targets are
  unchanged: they describe the service on a dedicated CPU. Meeting them in production takes more CPU,
  not code changes.
