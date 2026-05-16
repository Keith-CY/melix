# Integration Swift binary resolution string-stat slice

## Goal

Reduce Linux-verifiable integration helper overhead when resolving Swift product
binaries from large `.build` directories. The slice keeps executable selection
semantics unchanged while avoiding per-candidate `Path` object construction on
the hot scan path.

## Probe coverage

The affected path is covered by the registered PR-scoped probe
`integration-swift-binary-resolution-scandir` in
`infra/perf/pr_scoped_probes.json`. The probe already exposes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `tests/integration/helpers.py`
- `tests/integration/test_helper_binary_resolution.py`
- `tests/integration/test_helper_remove_tree.py`
- `scripts/integration_swift_binary_resolution_probe.py`
- `scripts/integration_remove_tree_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Slice

`_newest_executable_swift_product_binary()` now keeps candidate paths as strings
while scanning and stats them with `os.stat()`. It converts only the final
selected candidate back to `Path`, preserving the public resolver return type,
mtime/depth tie breaker, executable checks, and missing-build-root behavior.

## Local evidence

Linux local registered probe (`scripts/integration_swift_binary_resolution_probe.py`,
three runs, default 5 samples/run, `candidate_count=1501`):

- base `elapsed_ms_mean` samples: `77.889960`, `75.589246`, `82.483022`
- head `elapsed_ms_mean` samples: `23.271438`, `23.711962`, `23.205934`
- aggregate base mean `78.654076 ms`; aggregate head mean `23.396445 ms`
- delta `-55.257631 ms` (`-70.25%`)
- base `peak_bytes_mean` average `3659.8`; head `peak_bytes_mean` average `2154.2`
- `candidate_count=1501` in all runs

Focused pytest and changed-scope coverage passed locally with 100% changed-line
coverage for the modified lines.
