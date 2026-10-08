# Reproducible benchmark

Measured on 2026-10-08 with Python 3.12 on a local Windows workstation, SQLite, the deterministic offline provider, and 100 sequential synthetic tasks.

| Metric | Result |
|---|---:|
| Successful tasks | 100 / 100 |
| Throughput | 42.93 tasks/s |
| Mean task latency | 18.916 ms |
| P50 task latency | 18.344 ms |
| P95 task latency | 24.025 ms |

Reproduce with `python scripts/benchmark.py --tasks 100`.

These numbers measure orchestration and persistence overhead, not remote-model latency or horizontal scalability. Results vary by filesystem and CPU. The benchmark fails if any task does not reach `completed`.

