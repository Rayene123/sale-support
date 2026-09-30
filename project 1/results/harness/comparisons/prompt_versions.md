# Prompt version comparison

- runs: results\harness\dev-v1-replay, results\harness\dev-v2-replay, results\harness\dev-v3-replay
- legacy: C:\Users\flash\sale-support\project 1\results\judge-comparison-v2-20260929\comparison.json

| prompt | run           | items | judged | avg /8 | delta | avg system ms | p95 system ms | system tokens | judge tokens | cost USD |
|--------|---------------|-------|--------|--------|-------|---------------|---------------|---------------|--------------|----------|
| v1     | dev-v1-replay | 40    | 40     | 7.850  | 0.000 | 3908.3        | 7629.0        | 28466         | 49463        | n/a      |
| v1     | legacy_v1     | 40    | 40     | 7.850  | 0.000 | 3908.3        | 7629.0        | 28466         | None         | n/a      |
| v2     | dev-v2-replay | 40    | 40     | 7.875  | 0.025 | 4570.2        | 7854.7        | 35318         | 48708        | n/a      |
| v2     | legacy_v2     | 40    | 40     | 7.875  | 0.025 | 4570.2        | 7854.7        | 35318         | None         | n/a      |
| v3     | dev-v3-replay | 40    | 40     | 7.925  | 0.075 | 5757.3        | 9859.1        | 39823         | 48267        | n/a      |
| v3     | legacy_v3     | 40    | 40     | 7.925  | 0.075 | 5757.3        | 9859.1        | 39823         | None         | n/a      |

Score distributions:

- **v1** (dev-v1-replay): 3/8: 1, 7/8: 1, 8/8: 38
- **v1** (legacy_v1): 3/8: 1, 7/8: 1, 8/8: 38
- **v2** (dev-v2-replay): 3/8: 1, 8/8: 39
- **v2** (legacy_v2): 3/8: 1, 8/8: 39
- **v3** (dev-v3-replay): 6/8: 1, 7/8: 1, 8/8: 38
- **v3** (legacy_v3): 6/8: 1, 7/8: 1, 8/8: 38

Notes:

- Scores are model-assigned unless the run attests independent human review.
- Averages are computed over graded items only; check coverage before comparing.
- Latency and tokens differ by hardware and provider; do not read them as quality.
- `legacy_*` rows come from saved files, not from a fresh run of this harness.
