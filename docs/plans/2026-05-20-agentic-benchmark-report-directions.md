# Agentic Benchmark Report Direction Plan

## Goal

Define direction-aware benchmark report semantics for agentic tool-turn cost and
fatal outcome metrics added for OpenSearch-VL alignment.

## Scope

- Covers issue #707 under the OpenSearch-VL agentic benchmark metrics direction.
- Updates report direction semantics for the request and matrix metrics added by
  `docs/plans/2026-05-20-agentic-benchmark-tool-turn-fields.md`.
- Keeps schema additions, export field additions, and new benchmark suite
  catalog entries out of scope.

## Architecture

The benchmark report already normalizes matrix and request probes into metric
keys with aggregation suffixes. This slice makes the agentic tool-turn suffixes
first-class entries in the explicit direction map so report rows do not depend
on broad substring heuristics for fatal-rate or tool-turn cost semantics.

Agentic tool-turn metrics are treated as matched-context cost and reliability
signals:

- `tool_call_count`, `turn_count`, `agentic_tool.call_count`,
  `agentic_tool.observation_count`, and `agentic_tool.completed_count` are
  trajectory-cost counts. Lower is better when benchmark context and task set
  are held constant.
- `tool_latency_ms` and `agentic_tool.latency_ms` are execution latency. Lower
  is better.
- `observation_bytes` and `agentic_tool.observation_emitted_bytes` are emitted
  observation payload size. Lower is better.
- `fatal_rate`, `agentic_tool.timeout_count`, and
  `agentic_tool.failed_count` are reliability failures. Lower is better.

Quality and task success remain governed by existing success-rate, typed-score,
pass-rate, and evaluation metrics. The tool-turn direction entries only compare
the cost and failure shape of matched benchmark trajectories.

## Performance Probes And Metrics

- Measurement points:
  - report metric rows built by
    `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
  - benchmark context rows and matrix request rows containing agentic
    `tool_call_count`, `tool_latency_ms`, `observation_bytes`, `fatal_rate`,
    and `turn_count`
  - nested `agentic_tool_metrics` evidence keys collected by the report
- Success metrics:
  - each agentic report suffix has an explicit direction entry.
  - fatal-rate, timeout-count, failed-count, latency, bytes, tool-call, and
    turn-count increases produce `warning` rows.
  - unchanged cache-hit and success-rate semantics remain higher-is-better.

## Verification

- `git diff --check`
- Focused Python report tests:
  - `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
- Changed-scope coverage for
  `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- Runtime report artifact under `.runtime/agentic-report-directions/` proving
  fatal-rate/tool-turn rows render with lower-is-better warning semantics.

## Known Gaps

- Fixture-backed agentic benchmark suite catalog entries are deferred to the
  later OpenSearch-VL alignment milestone.
