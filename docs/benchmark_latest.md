_Run 2026-11-19T13:58:03+00:00 on Windows-10-10.0.26200-SP0, 24 logical CPUs, Python 3.11.8. Everything ran on one machine._

### /score latency (ms)
| Scenario | n | Client p50 | p95 | p99 | max | Server p50 | p95 | p99 | Flagged |
|---|---|---|---|---|---|---|---|---|---|
| normal traffic | 5000 | 6.73 | 30.51 | 45.61 | 114.2 | 2.81 | 3.64 | 4.83 | 0% |
| high-risk (SHAP path) | 1000 | 8.94 | 51.89 | 67.36 | 118.7 | 5.02 | 6.08 | 6.89 | 100% |

### /score concurrency (ms)
| Clients | Req/s | Client p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|
| 4 | 86.4 | 46.25 | 69.71 | 79.46 | 0 |
| 16 | 86.5 | 183.62 | 197.7 | 212.78 | 0 |

### Stream throughput (XADD -> score -> Postgres commit)
| Run | Events | Seconds | Events/s |
|---|---|---|---|
| 1 | 20000 | 24.55 | 815 |
| 2 | 20000 | 23.37 | 856 |
| 3 | 20000 | 23.71 | 844 |

Median: **844 events/s** (single worker, batch size 100)

### End-to-end latency, enqueue to persisted decision
| Offered eps | % of capacity | Achieved eps | Probes | p50 ms | p95 | p99 | max | Timeouts |
|---|---|---|---|---|---|---|---|---|
| 0 | 0% | 0 | 61 | 98.06 | 107.85 | 119.6 | 119.6 | 0 |
| 210 | 25% | 210 | 57 | 107.49 | 134.45 | 202.18 | 202.18 | 0 |
| 420 | 50% | 420 | 56 | 113.05 | 129.86 | 210.32 | 210.32 | 0 |
| 680 | 81% | 681 | 50 | 126.44 | 233.8 | 263.86 | 263.86 | 0 |
