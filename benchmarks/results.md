# Local benchmark results

Measured on 2026-08-23 on the local Windows development machine with Python 3.14 and SQLite. Query results use 100,000 generated transaction rows and 25 repetitions. Times include fetching all selected rows.

| Query | Before median | Before p95 | After median | After p95 |
| --- | ---: | ---: | ---: | ---: |
| History page | 0.048 ms | 0.087 ms | 0.033 ms | 0.040 ms |
| Time range | 9.235 ms | 12.235 ms | 6.034 ms | 6.445 ms |
| Category range | 6.962 ms | 9.194 ms | 4.228 ms | 4.448 ms |
| Status aggregate | 5.518 ms | 6.251 ms | 1.185 ms | 1.219 ms |

The dataset/user ordering index improved the already-small history query by 31% at the median. Composite report filters improved the time-range median by 35%, category-range median by 39%, and status aggregate median by 79%. These are local measurements, not production capacity claims.

| Ingestion size | Duration | Throughput |
| ---: | ---: | ---: |
| 1,000 rows | 58.98 ms | 16,953.7 rows/s |
| 5,000 rows | 221.75 ms | 22,548.2 rows/s |
| 10,000 rows | 453.86 ms | 22,033.2 rows/s |

Ingestion measures validation plus the transactional staging/bulk-load path. Queue wait time is excluded.
