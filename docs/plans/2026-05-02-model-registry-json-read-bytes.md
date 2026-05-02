# Model registry JSON byte-read fast path

## Goal

Reduce JSON file ingestion overhead in `services/mlx-worker-python/worker/model_registry/catalog.py` by loading small model-registry JSON payloads from bytes instead of text-decoding them before handing them to `json.loads(...)`.

## Why this slice

The model registry scanner reads many `config.json` and `generation_config.json` files while building a registry snapshot. Python's JSON decoder accepts `bytes` directly, so using `Path.read_bytes()` avoids an intermediate text decode at the loader boundary while preserving the same JSON object semantics and cache invalidation behavior.

## Registered probe coverage

The affected path is already covered by the registered PR-scoped probe `model-registry-plain-local-manifest-stat-elision` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for the catalog path.

## Linux-only constraint

This slice stays inside Python code and can be verified locally on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe. No Swift/macOS runtime effect is claimed.

## Touched files

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-02-model-registry-json-read-bytes.md`

## Implementation tasks

1. Add a focused regression test proving `_load_json_dict_file(...)` reads JSON bytes and does not call `Path.read_text(...)`, while retaining cache reuse.
2. Change `_load_json_dict_file(...)` from `Path.read_text(encoding="utf-8")` to `Path.read_bytes()` before `json.loads(...)`.
3. Run the existing registered model-registry PR-scoped test, coverage, and probe commands locally.

## Success metrics

- Behavior remains identical for valid dictionary JSON payloads and existing cache hits.
- Registered probe `elapsed_ms_mean` should improve or remain within noise compared with the pre-change local baseline.
- Registered probe `manifest_is_file_calls_mean` remains `0.0`, proving the previous manifest-stat optimization is preserved.
