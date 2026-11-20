_Run 2026-11-19T18:50:46+00:00 on Windows-10-10.0.26200-SP0, 24 logical CPUs, Python 3.11.8. Everything ran on one machine._

### /score latency (ms)
| Scenario | n | Client p50 | p95 | p99 | max | Server p50 | p95 | p99 | Flagged |
|---|---|---|---|---|---|---|---|---|---|
| normal traffic | 5000 | 4.74 | 5.81 | 16.55 | 70.01 | 2.51 | 3.43 | 14.38 | 0% |
| high-risk (SHAP path) | 1000 | 6.76 | 8.02 | 22.96 | 34.74 | 4.28 | 5.36 | 20.51 | 100% |

### /score concurrency (ms)
| Clients | Req/s | Client p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|
| 4 | 235.5 | 16.22 | 23.25 | 34.34 | 0 |
| 16 | 242.7 | 64.25 | 82.44 | 112.65 | 0 |

### Stream throughput (XADD -> score -> Postgres commit)
| Run | Events | Seconds | Events/s |
|---|---|---|---|
| 1 | 20000 | 9.33 | 2143 |
| 2 | 20000 | 12.66 | 1580 |
| 3 | 20000 | 6.54 | 3060 |

Median: **2143 events/s** (single worker, batch size 100)

### End-to-end latency, enqueue to persisted decision
| Offered eps | % of capacity | Achieved eps | Probes | p50 ms | p95 | p99 | max | Timeouts |
|---|---|---|---|---|---|---|---|---|
| 0 | 0% | 0 | 69 | 93.77 | 155.55 | 182.42 | 182.42 | 0 |
| 540 | 25% | 536 | 51 | 149.27 | 223.63 | 250.0 | 250.0 | 0 |
| 1070 | 50% | 1068 | 88 | 24.72 | 116.4 | 130.78 | 130.78 | 0 |
| 1710 | 80% | 1714 | 74 | 50.44 | 138.07 | 152.43 | 152.43 | 0 |
