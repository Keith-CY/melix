# Engine Generate Sampling Stop Elision

## Scope

This Python-only performance slice keeps `EngineCore.generate` from allocating and copying a `SamplingConfig` when the resolved stop sequence tuple already matches the request sampling configuration.

Affected files:

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`

## Probe Coverage

The affected path is covered by the registered `engine-generate-usage-token-elision` PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`. The probe provides focused test, coverage, and command-json probe commands for the Python generate hot path.

## Plan

1. Preserve the existing clone-and-rewrite behavior when resolved stop sequences differ from the incoming sampling configuration.
2. Return the original sampling configuration when stop sequences already match, avoiding protobuf allocation and `CopyFrom` work on the common no-stop path.
3. Add regression tests for the identity-preserving fast path and the clone-on-change path.
4. Run focused pytest, changed-scope coverage, and the registered performance probe locally on Linux.

## Validation Boundary

This slice is Python-only and locally verifiable on Linux. GitHub Actions remains the merge gate for the registered PR-scoped performance workflow.
