# Local benchmark results

Measured on 2026-08-23 on the local Windows development machine with Python 3.14 and SQLite. Query results use 100,000 generated transaction rows, 10 unmeasured warm-up runs, and 25 measured repetitions. Times include fetching all selected rows.

| Query | Before median | Before p95 | After median | After p95 |
| --- | ---: | ---: | ---: | ---: |
| History page | 0.126 ms | 0.173 ms | 0.088 ms | 0.108 ms |
| Time range | 25.855 ms | 42.836 ms | 18.662 ms | 26.546 ms |
| Category range | 19.125 ms | 24.399 ms | 14.397 ms | 25.314 ms |
| Status aggregate | 18.860 ms | 30.297 ms | 5.653 ms | 7.056 ms |

The dataset/user ordering index improved the already-small history query by 30% at the median. Composite report filters improved the time-range median by 28%, category-range median by 25%, and status aggregate median by 70%. These are local measurements, not production capacity claims.

| Ingestion size | Duration | Throughput |
| ---: | ---: | ---: |
| 1,000 rows | 289.33 ms | 3,456.3 rows/s |
| 5,000 rows | 894.97 ms | 5,586.8 rows/s |
| 10,000 rows | 934.34 ms | 10,702.8 rows/s |

Ingestion measures validation plus the transactional staging/bulk-load path. Queue wait time is excluded.
