# Deterministic Image Edit Digest Reuse

## Goal

Reduce redundant hashing in the deterministic image edit runtime by computing edit source and mask digests once per request instead of once per generated variant.

## Linux-only constraint

This slice only touches the Python worker runtime and PR-scoped performance harness, so it is locally verifiable on Linux with focused pytest, changed-scope coverage, and a command-json performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- `services/mlx-worker-python/tests/test_image_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_image_edit_digest_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

Registered probe: `deterministic-image-edit-digest-reuse`

The probe runs `scripts/deterministic_image_edit_digest_probe.py`, which executes an eight-variant image edit using large source and mask buffers. It reports:

- `elapsed_ms_mean` (lower is better)
- `digest_calls_mean` (lower is better)
- `image_count`
- `payload_checksum`
- `sample_count`

## Success metrics

- Focused tests pass.
- Changed executable coverage for touched scope is at least 95%.
- Probe preserves output shape/checksum and reduces tracked source/mask digest calls from the old per-variant path to the request-local digest path.
- `git diff --check` passes.

## Verification commands

Use:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_image_runtime.py::test_image_edit_persists_lineage_and_generated_artifact \
  services/mlx-worker-python/tests/test_image_runtime.py::test_image_edit_reuses_input_digests_across_variants \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_image_edit_digest_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_deterministic_image_edit_digest_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json <touched files>

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/deterministic_image_edit_digest_probe.py
```
