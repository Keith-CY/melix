# Dataset registry JSON preview buffer reuse

## Scope

This Python-only performance slice targets limited JSON dataset previews in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`, specifically
`_limited_rows_from_json_file()`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries covering the
runtime source, dataset-registry tests, PR-scoped performance selection, and
`scripts/dataset_registry_preview_limit_probe.py`.

## Change

`_limited_rows_from_json_file()` incrementally reads JSON text chunks and tries
to decode enough rows before falling back to full-file decoding. The previous
loop stored chunks in a list and rebuilt the candidate text with
`"".join(chunks)` after every chunk. This slice keeps a single growing
`json_text` buffer instead, avoiding repeated list joins in chunk-heavy limited
preview files while preserving the same incremental decode boundaries and final
fallback behavior.

## Validation plan

1. Run the focused dataset-registry tests and PR-scoped performance registry
   tests from the registered probe.
2. Run changed-scope coverage for the changed source path, focused tests, probe
   registry tests, and probe script.
3. Run the registered local Linux probe against `origin/main` and this branch.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Local result

Local Linux validation on 2026-05-23 used the registered
`dataset-registry-preview-limit-short-circuit` commands.

- Focused tests:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q ...`
  - Result: `21 passed in 6.02s`.
- Changed-scope coverage:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ... && ... coverage json ... && python3 scripts/changed_scope_coverage.py ...`
  - Result: `21 passed in 0.44s`; changed-line coverage `2/2`, `100%`.
- Registered local probe comparison:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id dataset-registry-preview-limit-short-circuit --base-repo /root/.hermes/profiles/coder/workspace/melix --head-repo "$PWD" --output /tmp/dataset-json-preview-buffer-probe.json`

| Metric | Base (`origin/main`) | Head | Delta | Result |
| --- | ---: | ---: | ---: | --- |
| `elapsed_ms_mean` | `0.786728 ms` | `0.337241 ms` | `-0.449487 ms` (`-57.13%`) | improved |
| `zero_limit_elapsed_ms_mean` | `0.215863 ms` | `0.145031 ms` | `-0.070832 ms` (`-32.81%`) | improved |
| `peak_bytes_mean` | `39210.286 bytes` | `39178.286 bytes` | `-32.000 bytes` (`-0.08%`) | unchanged/slightly lower |
| `zero_limit_peak_bytes_mean` | `2048.0 bytes` | `2048.0 bytes` | `0 bytes` (`0.00%`) | unchanged |

Guardrails remained stable: `file_count=50000`, `rows_returned=1`,
`zero_limit_rows_returned=0`, and `sample_count=7` for both base and head.
