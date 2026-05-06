# Image Edit Input Digest Metadata Reuse

## Goal

Avoid hashing large image edit source and mask payloads twice in the deterministic image runtime. The edit path already needs source/mask SHA-256 values for generated payload lineage, and artifact metadata currently recomputes the same full digest for the persisted source/mask artifacts.

## Touched Files

- `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- `services/mlx-worker-python/tests/test_image_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-06-image-edit-input-digest-metadata-reuse.md`

## Linux-only Constraint

This is a Python worker slice and can be verified locally on Linux with focused pytest, changed-scope coverage, and the existing deterministic image edit digest PR-scoped performance probe.

## Performance Probe

Reuse existing registered probe:

- `deterministic-image-edit-digest-reuse`
- `scripts/deterministic_image_edit_digest_probe.py`

The probe tracks SHA-256 calls for large source/mask edit inputs and reports elapsed time plus `digest_calls_mean`.

## Success Metrics

- Preserve image edit behavior, artifact metadata, lineage, and generated output payloads.
- Reduce tracked source/mask SHA-256 calls from 4 to 2 in the existing probe workload.
- Keep changed-scope coverage at or above 95%.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_image_runtime.py::test_image_edit_persists_lineage_and_generated_artifact services/mlx-worker-python/tests/test_image_runtime.py::test_image_edit_reuses_input_digests_across_variants services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_image_edit_digest_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_image_runtime.py::test_image_edit_persists_lineage_and_generated_artifact services/mlx-worker-python/tests/test_image_runtime.py::test_image_edit_reuses_input_digests_across_variants services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_image_edit_digest_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o /tmp/image-digest-coverage.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/changed_scope_coverage.py --coverage-json /tmp/image-digest-coverage.json services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py services/mlx-worker-python/tests/test_image_runtime.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/deterministic_image_edit_digest_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --probe-id deterministic-image-edit-digest-reuse --output /tmp/deterministic-image-edit-digest-reuse.json
```
