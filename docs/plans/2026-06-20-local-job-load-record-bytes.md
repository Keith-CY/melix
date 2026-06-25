# Local job continuation record byte-load slice

This Python-only performance slice is limited to `LocalJobContinuationStore.load_record()` in `worker.runtime.local_job_continuation`.

## Scope

The local-job follow-up scan reads one JSON record per candidate job. The current scan path is already registered and optimized around `os.scandir()`, but each `load_record()` call still decodes the record file to text before handing it to `json.loads()`. Python's JSON loader accepts UTF-8 bytes directly, so the scan can avoid a separate text decode while preserving the record schema and validation behavior.

No record schema, reconciliation, claim, projection, or follow-up admission behavior changes in this slice.

## Registered probe

The affected path is covered by the registered PR-scoped probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/local_job_continuation.py`
- `services/mlx-worker-python/tests/test_local_job_continuation.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/local_job_followup_scan_probe.py`

## Implementation plan

1. Add regression coverage proving `load_record()` does not use `Path.read_text()` on the hot scan path.
2. Switch `load_record()` to `Path.read_bytes()` and pass the bytes to `json.loads()`.
3. Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.

## 2026-06-25 follow-up: direct binary open

This follow-up keeps the same registered `local-job-followup-scan-scandir` probe and narrows the already byte-oriented `load_record()` hot path by replacing the `Path.read_bytes()` convenience wrapper with a direct `open(path, "rb").read()` call. The record still enters `json.loads()` as bytes, and missing-record behavior still returns `None` on `FileNotFoundError`; no schema, reconciliation, claim, projection, or admission behavior changes.

The focused regression guard monkeypatches `Path.read_bytes()` so the scan/load path cannot silently drift back to the wrapper when iterating large continuation stores.

## Validation boundary

This is a Python-only slice and is locally verifiable on Linux. GitHub Actions remains the final registered PR-scoped performance validation and merge gate.
