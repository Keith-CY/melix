# Code evaluation stdio read-only flag binding

## Scope

This Python-only performance slice is limited to the code-evaluation stdio tail
reader in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `code-eval-stdio-tail-single-stat` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the stdio tail reader and sandbox profile helpers.

## Optimization slice

`_read_limited_stdio(...)` already receives cached `os.open`, `os.fstat`,
`os.pread`, `os.read`, and `os.close` bindings through default arguments. This
slice extends the same pattern to the `os.O_RDONLY` flag so the hot stdio tail
loop avoids a module-global lookup for every open while preserving the same file
descriptor flags, tail decoding, size reporting, and error handling behavior.

## Verification plan

Run the focused registered test command, changed-scope coverage command, and the
registered probe locally on Linux. GitHub Actions PR-scoped performance remains
the merge gate after the PR opens.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
effect is claimed.

## 2026-08-24 sandbox temp filter binding slice

Follow-up slice: `_sandbox_temp_root_read_filters(...)` now reuses local default
bindings for `json.dumps`, `os.path.realpath`, `Path`, and `str` while preserving
the duplicate resolved-path elision and fallback behavior for path-like test
doubles. The same registered probe, `code-eval-stdio-tail-single-stat`, covers
this sandbox profile helper through its focused tests, changed-scope coverage,
and `sandbox_profile_elapsed_ms_mean` metric.

## 2026-08-25 sandbox profile temp-root text reuse slice

Follow-up slice: `_sandbox_profile(...)` now converts and quotes `temp_root` once,
passes that text into `_sandbox_temp_root_read_filters(...)`, and reuses the same
quoted value for the write-subpath filter. The read filter helper keeps its
previous public behavior when called directly, while the sandbox-profile hot path
avoids a second `str(Path)` conversion, one repeated `json.dumps(...)`, and binds
`json.dumps`/`str` through defaults. The registered
`code-eval-stdio-tail-single-stat` probe measures this through its
`sandbox_profile_elapsed_ms_mean` metric locally on Linux and in PR-scoped CI.
