# Plan: model registry Hugging Face ref byte reads

## Goal

Avoid the extra text-decoding wrapper on Hugging Face cache ref files while preserving nested ref discovery and revision fallback behavior.

## Scope

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This is a Python-only slice and is locally verifiable on Linux. No Swift or macOS runtime effect is claimed for this change.

## Registered probe

Reuse and extend the registered PR-scoped probe:

- Probe ID: `model-registry-plain-local-manifest-stat-elision`
- Registry: `infra/perf/pr_scoped_probes.json`
- The probe already covers `worker/model_registry/catalog.py` and includes focused `test_command`, `coverage_command`, and `probe_command` entries.

This slice extends the probe payload with one synthetic Hugging Face cache repo and records `hf_ref_read_text_calls_mean`, proving the optimized head path no longer calls `Path.read_text()` for HF ref files.

## Intended change

- Change `_hf_cache_revision_map(...)` to read ref payloads with `Path.read_bytes().strip().decode("utf-8")`.
- Preserve the existing `OSError` skip behavior and skip invalid UTF-8 ref payloads.
- Update focused tests to assert byte reads are used and text reads are not required for valid refs.
- Keep the optimization to this single file-read hot path.

## Success metrics

- Focused tests pass.
- Changed-scope coverage remains at least 95%.
- Registered probe reports `hf_ref_read_text_calls_mean=0.0` for the head path and a successful base/head comparison.
- `git diff --check` passes.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_reads_ref_bytes_once_and_preserves_nested_ref_names \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_reads_only_needed_snapshot_refs_and_can_early_exit \
  services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_skips_invalid_utf8_ref_bytes \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id model-registry-plain-local-manifest-stat-elision \
  --base-repo /tmp/melix-model-registry-hf-ref-base \
  --head-repo "$PWD" \
  --output /tmp/model-registry-hf-ref-probe.json

git diff --check
```
