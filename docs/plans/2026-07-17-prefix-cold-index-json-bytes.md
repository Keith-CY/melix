# Prefix cold index JSON bytes decode

## Scope

This Python-only performance slice is limited to `ColdPrefixStore._ensure_loaded_locked()` cold-index reloads in `services/mlx-worker-python/worker/runtime/prefix_block_store.py`. The registered probe models a cold directory with valid snapshot sidecars plus orphaned metadata files.

The current reload path already uses a single `os.scandir()` pass, reuses scandir-provided metadata and snapshot names, and iterates metadata sidecars in scan order. This follow-up changes valid metadata decoding from `json.load()` on a text file object to reading metadata bytes and passing them to `json.loads()`. The behavior is unchanged for valid metadata, orphan cleanup, and malformed metadata removal, but the hot reload path avoids the text wrapper plus per-file `json.load()` call overhead.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `prefix-cold-index-scandir` in `infra/perf/pr_scoped_probes.json`. The entry has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `json_load_calls_mean`, `path_glob_calls_mean`, and `scandir_calls_mean`.

## Optimization plan

1. Keep collecting metadata rows and snapshot names from one `os.scandir()` pass.
2. Decode valid metadata by reading bytes and using `json.loads()` instead of `json.load()` on a text file object.
3. Preserve orphan removal before decode, valid metadata parsing, no-`Path.glob()` behavior, and `stored_at`-based budget eviction semantics.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.
5. Use GitHub Actions PR-scoped performance as the registered probe merge gate.

## Verification

- Focused cold-prefix tests pass, including a regression guard proving reload uses byte payloads and does not call `json.load()` for valid metadata.
- Changed-scope coverage for touched Python/test/probe/registry files remains at or above 95%.
- Local registered probe should keep `path_glob_calls_mean=0` and `scandir_calls_mean=1`, reduce `json_load_calls_mean` to `0`, and improve or stay stable on `elapsed_ms_mean`; CI remains the merge-gate source of truth for the registered probe report.

## Follow-up: Token id list fast path

The 2026-07-19 follow-up keeps the same registered probe and stays inside
`ColdPrefixStore._ensure_loaded_locked()`. Metadata written by `ColdPrefixStore.store()`
already serializes `token_ids` as JSON integer arrays, so cold-index reload can
copy that common all-int list directly instead of coercing each token through
`int()` on every valid sidecar. The fallback path still coerces non-int metadata
values so manually edited or older string-token sidecars preserve existing
behavior.

Success remains the same: focused cold-prefix tests, changed-scope coverage, and
the registered Linux probe must pass locally, and the PR-scoped CI probe remains
the merge gate.
