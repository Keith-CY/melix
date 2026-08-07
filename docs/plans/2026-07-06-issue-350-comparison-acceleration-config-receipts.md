# Issue 350 Comparison Acceleration Config Receipts

## Goal

Carry the resolved acceleration config receipt into baseline-vs-accelerated
evidence artifacts so a performance comparison records exactly which
acceleration contract each run used.

## Scope

This slice connects the diagnostics-only `serving_acceleration_config` receipt
to the existing baseline-vs-accelerated evidence workflow.

In scope:

- Extend `ServingEvidenceRun` with an optional
  `serving_acceleration_config` mapping.
- Persist that mapping under each run in `baseline-vs-accelerated.json` when
  upstream code provides it.
- Add a compact `acceleration_configs` methodology section with `baseline` and
  `accelerated` entries so operators can inspect the compared methods without
  digging into each run.
- Update the serving diagnostics runbook with the comparison artifact fields.
- Cover the behavior with focused Python tests.

Out of scope:

- Requiring all existing comparison callers to provide the receipt.
- Synthesizing acceleration configs during artifact writing.
- Changing runtime admission, worker dispatch, sampler behavior, model loading,
  or benchmark execution.
- New protobuf fields or generated artifacts.

## Architecture

The existing comparison writer already owns claim-safe identity checks and
serializes `ServingEvidenceRun` objects. This slice keeps the writer passive:
it records a stable JSON object supplied by upstream diagnostics or benchmark
code and never probes runtime state. The methodology section mirrors the two
per-run receipts so automated report readers can compare the baseline and
accelerated contracts directly.

## Test Plan

Follow TDD:

1. Add a failing Python test in `test_serving_diagnostics.py` that builds a
   baseline run with a baseline `serving_acceleration_config` and an accelerated
   run with a speculative config. Assert both run payloads preserve the
   receipts and `methodology.acceleration_configs` contains the same two
   objects.
2. Add a regression assertion that omitted receipts serialize as empty objects,
   preserving current callers.
3. Implement the minimal `ServingEvidenceRun` field and methodology mapping.
4. Update `docs/runbooks/serving-diagnostics-evidence.md`.

Focused verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
```

Changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/tests/test_serving_diagnostics.py
```

Before PR:

```bash
git diff --check
.githooks/pre-commit
```

## Performance And Metrics

The changed path is artifact serialization for opted-in comparison evidence. It
adds at most two stable JSON object copies per comparison artifact and no
request hot-path work. Success metrics are focused tests, at least 95% measured
changed-line coverage for touched Python scope, and a PR-scoped performance
report with status `ok` and 0 regressions.

## Implementation Evidence

- RED: the focused comparison test failed because `ServingEvidenceRun` did not
  accept `serving_acceleration_config`.
- GREEN: the focused comparison test passed after adding the field, per-run
  serialization, and methodology mirroring.
- Focused diagnostics suite:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py`
  passed with 62 tests.
- Focused VLM comparison caller tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_artifact_requires_matched_identity services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_artifact_records_route_metrics services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_metrics_blocks_missing_context_and_identity_errors services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_metrics_writes_matched_artifact services/mlx-worker-python/tests/test_maintenance_service.py::test_vlm_batch1_comparison_reason_code_covers_blockers`
  passed with 13 tests.
- Changed-line coverage for touched Python scope:
  `TOTAL 14 0 100%`.
- Diff hygiene: `git diff --check` passed.
- Full pre-commit gate:
  `.githooks/pre-commit` passed. It ran `make swift-test`, `make py-test`,
  `make integration-test`, and the scoped performance probe
  `serving-diagnostics-debug-queue-bounds`.
- Final scoped performance report:
  `.runtime/pre-commit-performance/20260706-121705-3fcdf5de/report/report.md`
  reported `Status: ok`, `Regressions: 0`, `Verification failures: 0`, and
  100% changed-line coverage.
