# Quantization Index Shard Cached Read Slice

## Scope

This Python-only performance slice is limited to MLX-LM conversion smoke-file
selection in `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`.
The behavior remains unchanged: when a sharded `model.safetensors.index.json`
exists, the smoke check returns the index file plus the lexicographically first
non-empty shard name in the index `weight_map`. This follow-up keeps the byte
read path and caches parsed index results by index path, mtime, and size so
repeated smoke-file checks for an unchanged bundle avoid reparsing the same
large `weight_map`.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`quantization-index-shard-min-single-pass` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries covering:

- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantization_index_shard_probe.py`
- `scripts/changed_scope_coverage.py`

The probe builds a synthetic sharded index with thousands of weight-map entries
and records elapsed time, traced peak allocations, sorted-call count, index entry
count, iterations, and sample count.

## Implementation plan

- Keep loading `model.safetensors.index.json` with `Path.read_bytes()` and pass
  the bytes directly to `json.loads()` to avoid a separate text decode/string
  allocation.
- Cache the parsed first-shard tuple behind an `lru_cache` keyed by index path,
  `st_mtime_ns`, and `st_size`, preserving correctness when the index file is
  rewritten.
- Preserve the existing single-pass shard minimum scan and fallback behavior for
  unreadable, malformed, missing, or empty `weight_map` index files.
- Add focused regression coverage that proves repeated unchanged checks reuse the
  cached bytes parse and changed index metadata invalidates the cache.

## Verification plan

Run locally on Linux before pushing:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py::test_mlx_lm_source_and_smoke_file_helpers_cover_edge_cases services/mlx-worker-python/tests/test_quantization_pipeline.py::test_mlx_lm_index_weight_files_reads_index_as_bytes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_quantization_qat_source_scan_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantization_index_shard_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_quantization_pipeline.py::test_mlx_lm_source_and_smoke_file_helpers_cover_edge_cases services/mlx-worker-python/tests/test_quantization_pipeline.py::test_mlx_lm_index_weight_files_reads_index_as_bytes services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_quantization_qat_source_scan_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_quantization_index_shard_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/quantization_pipeline.py services/mlx-worker-python/tests/test_quantization_pipeline.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/quantization_index_shard_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_QUANTIZATION_INDEX_SHARD_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/quantization_index_shard_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id quantization-index-shard-min-single-pass --base-repo /root/.hermes/profiles/coder/workspace/worktrees/melix-base-quantization-index-shard-read-bytes-202605102100 --head-repo "$PWD" --output /tmp/quantization_index_shard_read_bytes_probe.json
```

GitHub Actions PR-scoped performance remains the merge gate for the registered
probe report.
