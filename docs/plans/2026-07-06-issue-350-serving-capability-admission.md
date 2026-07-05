# Issue 350 Serving Capability Admission Receipt Plan

## Goal

Add a diagnostics-only serving capability admission receipt to
`effective-config.json` so operators can inspect the resolved capability and
acceleration admission contract already evaluated by serving code.

## Scope

This slice covers the latest issue #350 executable slice: wire effective serving
capability and acceleration admission evidence into diagnostics bundles before
adding any new fast path.

In scope:

- Derive a top-level `serving_capability` receipt from complete namespaced
  metadata in serving diagnostics effective config.
- Preserve an explicit `serving_capability` receipt when the caller already
  provides one.
- Leave incomplete metadata untouched rather than synthesizing a partial
  receipt.
- Document the receipt fields in the serving diagnostics runbook.

Out of scope:

- New model routing or worker admission behavior.
- New speculative, assistant, or media fast paths.
- New protobuf schema fields.
- Installing or probing optional media dependencies during diagnostics bundle
  writing.

## Architecture

The Python diagnostics bundle writer already enriches `effective-config.json`
from existing metadata sources such as `execution_ext`, `request_metadata`,
`execution.ext`, and `worker_request.execution.ext`. This change extends that
same enrichment path with a stable `serving_capability` receipt. The bundle
writer remains diagnostics-only: it records facts supplied by upstream serving
paths and does not discover models, import optional packages, contact health
endpoints, or validate dependencies itself.

## Receipt Contract

When all required metadata keys are present, diagnostics should synthesize:

```json
{
  "serving_capability": {
    "schema_version": "melix.serving_capability_receipt.v1",
    "capabilities": ["generate_text"],
    "input_modalities": ["text"],
    "output_modalities": ["text"],
    "acceleration_profile": "balanced",
    "requested_mode": "baseline",
    "resolved_mode": "baseline",
    "optional_dependency_source": "not_required",
    "unsupported_reason": "none",
    "ignored_flags": [],
    "fallback_policy": "fail_closed"
  }
}
```

Required metadata keys:

- `melix.serving.capability.schema_version`
- `melix.serving.capability.capabilities`
- `melix.serving.capability.input_modalities`
- `melix.serving.capability.output_modalities`
- `melix.serving.capability.acceleration_profile`
- `melix.serving.capability.requested_mode`
- `melix.serving.capability.resolved_mode`
- `melix.serving.capability.optional_dependency_source`
- `melix.serving.capability.unsupported_reason`
- `melix.serving.capability.ignored_flags`
- `melix.serving.capability.fallback_policy`

List fields use comma-separated metadata strings and should normalize whitespace
and empty elements. `ignored_flags` may be an empty string and should become an
empty list.

## Performance And Observability

Observability mode: debug diagnostics. The changed path is bounded JSON
normalization during bundle writing. Success metrics:

- Changed-scope coverage for the diagnostics writer and tests is at least 95%.
- The existing serving diagnostics focused tests pass.
- The repository pre-commit scoped performance report has status `ok` with no
  regressions.

## Implementation Steps

1. Add a failing Python test that writes a diagnostics bundle with complete
   `melix.serving.capability.*` metadata under `worker_request.execution.ext`
   and asserts a stable top-level `serving_capability` receipt with normalized
   list fields.
2. Add a failing Python test that incomplete capability metadata does not create
   `serving_capability`.
3. Implement metadata mapping and list normalization in the serving diagnostics
   writer using the same source precedence pattern as `serving_profile` and
   `serving_readiness`.
4. Update the serving diagnostics runbook with the new receipt shape, required
   metadata keys, and diagnostics-only safety rule.
5. Run focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
```

6. Run changed-scope coverage:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/tests/test_serving_diagnostics.py
```

7. Run diff hygiene:

```bash
git diff --check
git diff --cached --check
```

8. Before commit, run the versioned pre-commit hook so it performs the full
   local gate and scoped performance report on this macOS host:

```bash
.githooks/pre-commit
```

9. Create a PR against issue #350 with the plan, commands, coverage, metrics,
   observability mode, and known gaps recorded in the PR template.
