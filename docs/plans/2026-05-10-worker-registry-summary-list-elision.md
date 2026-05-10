# Worker registry loaded summary builder lookup elision

## Goal

Reduce repeated bound-method lookup overhead in the loaded-model listing hot path by binding the summary protobuf builder once per listing call.

## Linux-only constraint

This is a Python worker slice. It is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered worker registry PR-scoped performance probe. No Swift runtime effect is claimed for this slice.

## Registered probe

Existing registered probe: `worker-registry-resident-bytes-accumulator` in `infra/perf/pr_scoped_probes.json`.

The probe already covers this path through repeated `list_loaded_models()` and `list_loaded_model_summaries()` calls against a 2,000-model synthetic registry and reports:

- `loaded_model_listing_elapsed_ms_mean` — lower is better.
- `loaded_model_listing_sort_calls_mean` — lower is better / regression guard for sorted-handle cache reuse.

The probe has focused `test_command`, `coverage_command`, and `probe_command` entries.

## Implementation approach

- Keep sorted handle caching and the `LoadedModel` snapshot unchanged.
- Bind `self._loaded_model_summary` to a local variable before constructing summary protobufs.
- Do not change handle ordering, registry mutation semantics, protobuf fields, or resident-byte accounting.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q ...focused worker registry tests...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ...focused tests... && coverage json ... && python3 scripts/changed_scope_coverage.py ...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/worker_registry_resident_probe.py`
- `git diff --check`
