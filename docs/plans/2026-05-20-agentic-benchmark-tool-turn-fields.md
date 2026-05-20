# Agentic Benchmark Tool-Turn Field Plan

## Goal

Add explicit benchmark schema fields that let operators localize agentic
tool-use cost and failure shape at the request and matrix-cell levels.

## Scope

- Covers issue #706 under the OpenSearch-VL agentic benchmark metrics direction.
- Adds additive fields to benchmark row schemas and persisted CSV/JSONL outputs:
  `tool_call_count`, `tool_latency_ms`, `observation_bytes`, `fatal_rate`, and
  `turn_count`.
- Keeps direction-aware report semantics for these fields out of scope for
  issue #707.

## Architecture

Benchmark rows already preserve full `agentic_tool_metrics` evidence blocks for
debugging. This slice projects the stable operator-facing subset into canonical
row fields so CSV exports, matrix summaries, and control-plane payloads do not
depend on parsing nested tool evidence.

Request-level fields are derived directly from the unified agentic tool runtime:

- `tool_call_count`: number of assistant tool calls for the request.
- `tool_latency_ms`: total deterministic adapter execution latency for the
  request.
- `observation_bytes`: emitted observation bytes for the request.
- `fatal_rate`: `1.0` when any executed tool observation timed out or failed,
  otherwise `0.0`; non-agentic requests default to `0.0`.
- `turn_count`: request turns attributable to the agentic exchange, computed as
  assistant tool-call turns plus tool observation turns.

Matrix summary rows aggregate those request fields:

- counts and bytes are summed across cell requests.
- `tool_latency_ms` is summed so the cell-level value represents total tool
  adapter time.
- `fatal_rate` is the fraction of cell requests with a fatal tool outcome.
- `turn_count` is summed across cell requests.

Legacy serving benchmark context and batch rows carry the same request-level
fields so existing export/report paths do not split the benchmark contract.

## Performance Probes And Metrics

- Measurement points:
  - agentic tool execution path: `agentic_tool.latency_ms`
  - persisted request rows: `tool_call_count`, `tool_latency_ms`,
    `observation_bytes`, `fatal_rate`, `turn_count`
  - matrix summary rows: cell-level aggregate of the same fields
- Success metrics:
  - schema helper defaults remain backward-compatible for non-agentic rows.
  - persisted JSONL and CSV outputs include the new fields.
  - matrix summaries aggregate tool counts, latency, observation bytes, fatal
    rate, and turns from request rows.
  - protocol and Swift bridge payloads preserve matrix summary fields.

## Verification

- `git diff --check`
- `make proto`
- Focused Python tests:
  - `services/mlx-worker-python/tests/test_agentic_tools.py`
  - `services/mlx-worker-python/tests/test_benchmark_schemas.py`
  - `services/mlx-worker-python/tests/test_benchmark_store.py`
  - `services/mlx-worker-python/tests/test_benchmark_export.py`
  - `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`
  - `services/mlx-worker-python/tests/test_maintenance_service.py`
- Focused Swift tests:
  - `services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift`
  - `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
  - `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Changed-scope coverage for modified Python and Swift implementation files.

## Known Gaps

- Direction semantics for these metrics are intentionally deferred to issue
  #707.
- Fixture-backed agentic benchmark suite catalog entries are deferred to
  milestone 2.
