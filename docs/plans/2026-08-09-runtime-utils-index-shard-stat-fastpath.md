# Runtime utils indexed shard stat fast path

## Scope

This Python-only performance slice is limited to the indexed safetensors shard
path in `services/mlx-worker-python/worker/runtime/runtime_utils.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`.
That entry watches `runtime_utils.py`, `test_runtime_utils.py`,
`test_pr_scoped_performance.py`, the runtime-utils weight probe script, and a
runtime-utils weight plan, and it provides focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Optimization hypothesis

SLC safetensors index scans already iterate explicit shard names from
`model.safetensors.index.json`. The previous indexed loop delegated each unique
candidate to `_weight_file_size(...)`, which re-read `Path.name` and repeated the
same filename suffix check after the caller had already normalized and joined the
candidate path. This slice keeps the existing suffix guard, duplicate-shard
elision, absolute/relative path handling, OSError tolerance, and regular-file
filtering, but performs the indexed-path `stat()` inline after a local filename
check.

## Verification path

Run the registered runtime-utils focused tests, changed-scope coverage, and
`runtime_utils_top_level_weights_probe.py` locally on Linux. The expected signal
is lower `indexed_elapsed_ms_mean` in the registered probe while preserving byte
totals, duplicate-shard elision, absolute shard support, and whitespace-tolerant
legacy values.

## Success criteria

- Focused runtime-utils and PR-scoped probe tests pass.
- Changed-scope automated coverage for the touched paths is at least 95%.
- The local registered probe shows indexed-path improvement or a clear
  non-regression.
- GitHub Actions PR-scoped performance for
  `runtime-utils-top-level-weight-streaming` completes successfully before merge.
