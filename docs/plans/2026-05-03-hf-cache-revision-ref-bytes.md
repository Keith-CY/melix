# Task Plan

## Title

`hf cache revision ref bytes`

## Goal

Reduce repeated text-decoding overhead in `worker/model_registry/catalog.py::_hf_cache_revision_map(...)` by switching Hugging Face cache ref-file reads from `Path.read_text(...).strip()` to a bytes-based path that preserves current snapshot-ID semantics, then update the existing model-registry PR-scoped performance gate so the changed scope is covered in CI.

## Non-Goals

- Do not refactor unrelated model-registry discovery code.
- Do not change the model-registry probe ID or workflow topology.
- Do not broaden the slice beyond `_hf_cache_revision_map(...)`, its focused tests, and the existing model-registry scoped-probe entry.

## Context

- Relevant specs: `AGENTS.md`, `docs/engineering-standards.md`, `docs/contributing.md`, `.github/pull_request_template.md`
- Relevant code paths:
  - `services/mlx-worker-python/worker/model_registry/catalog.py`
  - `services/mlx-worker-python/tests/test_model_registry_catalog.py`
  - `infra/perf/pr_scoped_probes.json`
- Current constraints:
  - Host is Linux; verification must be local for the touched Python scope.
  - Changed executable scope must reach at least 95% automated coverage before commit.
  - Because the scoped-probe registry entry already covers `catalog.py`, the safest CI path is to update that existing probe entry rather than introducing a second catalog probe ID.

## Assumptions

- `Path.read_bytes().strip().decode("utf-8")` preserves the current observable semantics for ref files that currently pass through `read_text(...).strip()`.
- The existing model-registry command-json probe can be extended to include a synthetic HF cache refs workload while retaining its current invalid-manifest metrics and ID.

## Work Plan

1. Add a tiny helper for reading a snapshot ID from HF cache ref files via bytes, and route `_hf_cache_revision_map(...)` through it.
2. Update focused catalog tests so they prove ref reads no longer use `Path.read_text(...)`, preserve nested-ref and early-exit behavior, and keep fallback behavior unchanged.
3. Update the existing `model-registry-plain-local-manifest-stat-elision` scoped-probe entry so its focused pytest/coverage commands include the new ref-read tests and its synthetic command-json workload also reports the HF cache ref-scan path.
4. Run focused pytest, changed-scope coverage, explicit local performance measurements, `git diff --check`, and a local base-vs-head scoped probe comparison before commit.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_reads_refs_once_and_preserves_nested_ref_names services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_reads_only_needed_snapshot_refs_and_can_early_exit services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_uses_recursive_scandir_without_rglob services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_reads_ref_bytes_without_text_decode services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_reads_refs_once_and_preserves_nested_ref_names services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_reads_only_needed_snapshot_refs_and_can_early_exit services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_uses_recursive_scandir_without_rglob services/mlx-worker-python/tests/test_model_registry_catalog.py::test_hf_cache_revision_map_reads_ref_bytes_without_text_decode services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_model_registry_catalog_probe_command_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/tests/test_model_registry_catalog.py
python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-registry-plain-local-manifest-stat-elision --base-repo <origin-main-worktree> --head-repo "$PWD" --output /tmp/model-registry-probe.json
git diff --check
```

## Acceptance Criteria

- `_hf_cache_revision_map(...)` no longer uses `Path.read_text(...)` for ref-file ingestion.
- Nested ref-name preservation, early exit, and unreadable-enumeration fallback behavior remain unchanged.
- Changed executable line coverage for `catalog.py` and its focused tests is at least 95%.
- Local explicit measurements show the HF cache ref-read path is measurably better or at least the registered scoped probe improves on the updated workload.

## Rollback or Safe Exit

- If the bytes-based ref reader changes semantics, regresses the explicit measurements, or makes the scoped probe comparison noisy/regressive, revert the slice and leave the worktree clean without pushing a PR.
