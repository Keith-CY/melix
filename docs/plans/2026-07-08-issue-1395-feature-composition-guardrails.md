# Issue 1395 Feature Composition Guardrails

## Issue

GitHub issue: [#1395](https://github.com/Keith-CY/melix/issues/1395)

## Goal

Add deterministic control-plane guardrails for composing SSD or disk-backed
expert-streaming style serving with speculative decoding. The guardrail must
turn potentially unsafe high fan-out configurations into observable, bounded
worker requests and preserve enough metadata for benchmark and evaluation
exports to explain what happened.

## Scope

In scope:

- Add a feature-composition guardrail receipt for speculative decoding combined
  with disk-backed serving or explicit expert streaming.
- Apply the guardrail in the request coordinator before worker dispatch.
- Cap speculative draft fan-out when the composition is active.
- Tighten the effective cache budget when the estimated main plus draft
  footprint crosses a configured threshold, and apply that budget through the
  worker request cache hints.
- Downgrade unsafe compositions to baseline when no safe effective cache budget
  remains.
- Add a per-request worker `CacheHints.cache_memory_budget_bytes` field for
  guardrail-applied cache budgets.
- Export guardrail request-level fields through benchmark matrix schemas and
  evaluation report aggregation.
- Document the receipt fields and benchmark probes.

Out of scope:

- Implementing real SSD expert streaming.
- Changing sampler, attention, or model-load internals.
- Claiming throughput, latency, or memory improvements.

## Receipt Contract

The control plane emits the following worker execution metadata keys:

- `melix.acceleration.feature_guardrail.schema_version`
- `melix.acceleration.feature_guardrail.composition`
- `melix.acceleration.feature_guardrail.decision`
- `melix.acceleration.feature_guardrail.requested_num_draft_tokens`
- `melix.acceleration.feature_guardrail.effective_num_draft_tokens`
- `melix.acceleration.feature_guardrail.resource_fanout_estimate`
- `melix.acceleration.feature_guardrail.requested_cache_budget_bytes`
- `melix.acceleration.feature_guardrail.effective_cache_budget_bytes`
- `melix.acceleration.feature_guardrail.guardrail_reason`

The schema version is `melix.feature_composition_guardrail.v1`.

`composition` is `ssd_expert_streaming_x_speculative_decode` when speculative
decoding is combined with disk-backed serving or explicit expert streaming.
Otherwise it is `none`.

`decision` is one of:

- `accept`
- `auto_cap_draft_tokens`
- `tighten_cache_budget`
- `auto_cap_draft_tokens_and_tighten_cache_budget`
- `refuse_unsafe_composition`

## Policy

The composition is active when the resolved acceleration mode is
`speculative_decode` and either condition is true:

- the model disk streaming mode is `prefer_disk` or `require_disk`
- model or request metadata sets
  `melix.acceleration.expert_streaming.enabled=true`

The resource fan-out estimate is `1 + effective_num_draft_tokens`.

When the composition is active and the requested draft token count is greater
than one, the control plane caps the effective token count to one and records
`auto_cap_draft_tokens`.

When the configured main plus draft footprint estimate crosses
`melix.acceleration.feature_guardrail.memory_threshold_bytes`, the control plane
tightens the effective cache budget to half the requested cache budget, bounded
by `melix.acceleration.feature_guardrail.min_cache_budget_bytes`, and records
`tighten_cache_budget` unless draft fan-out was already capped. If both controls
apply, the decision is `auto_cap_draft_tokens_and_tighten_cache_budget` and the
reason is
`disk_streaming_speculative_fanout_cap_and_main_draft_footprint_exceeds_threshold`.

When the effective cache budget is lower than the requested model cache budget,
the request coordinator writes it to
`execution.cache_hints.cache_memory_budget_bytes` before dispatch. The Python
worker forwards that value to the native MTP text runtime as
`_melix.cache_memory_budget_bytes`; the runtime treats it as a per-request LCP
cache write ceiling and skips storing a prompt-cache snapshot whose estimated
size exceeds the budget.

When the effective cache budget is below
`melix.acceleration.feature_guardrail.min_safe_cache_budget_bytes`, the control
plane downgrades the worker request to baseline and records
`refuse_unsafe_composition`.

## Benchmark Fields

Benchmark matrix request rows preserve these request-level fields:

- `feature_guardrail_requested_num_draft_tokens`
- `feature_guardrail_effective_num_draft_tokens`
- `feature_guardrail_resource_fanout_estimate`
- `feature_guardrail_requested_cache_budget_bytes`
- `feature_guardrail_effective_cache_budget_bytes`
- `feature_guardrail_reason`

The numeric fields are aggregated by the benchmark evaluation report. The
string reason is preserved in exports but not aggregated as a metric.

## Verification Plan

Focused verification:

- `xcrun swift test --no-parallel --package-path services/control-plane-swift --filter ModelCatalogTests`
- `xcrun swift test --no-parallel --package-path services/control-plane-swift --filter RequestCoordinatorTests`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_evaluation_report.py services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_mlx_backend.py`
- `make proto`
- `git diff --check`

Before commit and PR:

- `.githooks/pre-commit`

## Cross-Linking

After the pull request exists, link the PR or plan from closed umbrella issues
[#350](https://github.com/Keith-CY/melix/issues/350) and
[#40](https://github.com/Keith-CY/melix/issues/40) so the closed acceleration
tracking history points to the guardrail slice.
