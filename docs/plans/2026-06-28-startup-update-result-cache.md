# Startup update result cache slice

This Python performance slice is limited to `worker.productization.startup_signals.check_for_updates(...)`.

## Goal

Keep update-check behavior unchanged while avoiding repeated channel JSON decode,
`UpdateCheckResult` allocation, and version comparison work for repeated checks
against the same stat-valid channel file and installed version. The channel file
stat/cache path remains the source of freshness for `latest_version` and
`channel`; this slice memoizes the immutable final result tuple only while the
channel file `mtime_ns` and size are unchanged.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`. The registered entry already includes focused `test_command`, `coverage_command`, and `probe_command` commands, and the `update_channel_*` / `update_result_*` metrics cover repeated update-check result construction.

## Verification plan

1. Add regression tests proving repeated checks reuse the stat-valid cached
   result before re-decoding channel JSON, and that a changed channel file
   refreshes the cached result.
2. Run the registered focused test command for `startup-signals-version-compare-single-pass`.
3. Run the registered changed-scope coverage command.
4. Run the registered probe locally on Linux and use the PR-scoped performance workflow as the merge gate.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime behavior changes are included.

## 2026-07-01 follow-up: repeated version-pair cache

The next focused Python slice keeps the same registered probe and narrows the
optimization to repeated `compare_versions(left, right)` pairs. Startup update
checks and the registered probe repeatedly compare identical installed/latest
version strings while the channel file remains stat-valid. Decorating
`compare_versions` with a bounded `lru_cache` preserves the existing parsing and
normalization semantics for cold pairs while letting hot repeated pairs return
without rescanning the version strings.

The cache is intentionally bounded (`16_384` entries) so the registered probe's
12k comparison corpus fits while long-running processes cannot grow the cache
unbounded. Verification remains the existing focused startup-signals test,
coverage, and registered local probe commands, followed by the PR-scoped
performance workflow as the merge gate.

## 2026-07-03 follow-up: product version pyproject path cache

This Python-only follow-up stays inside the same registered probe and narrows to
`read_product_version(...)`. Repeated startup checks already reuse the parsed
product version while the `pyproject.toml` stat tuple is unchanged, but each call
still rebuilt the same `root / "pyproject.toml"` `Path` before statting the file.
This slice caches the derived pyproject path by resolved repository root text,
then keeps the existing mtime/size/version cache as the freshness source. The
behavior remains unchanged for relative inputs because they are still resolved
before the path-cache lookup; absolute `Path` inputs continue to avoid an extra
`resolve()` call.

Validation remains the registered focused pytest selection, changed-scope
coverage, and the registered local/CI probe for startup signal version checks.

Local 2026-07-03 probe decision for this pyproject path-cache slice:

- Baseline `product_version_elapsed_ms_mean`: `690.2703012705648`, `662.0320463220456`, `660.4938739910722` ms; mean `670.9320738612275` ms.
- Post-change `product_version_elapsed_ms_mean`: `194.25131743108588`, `193.8522669786055`, `190.22479472083174` ms; mean `192.77612637684104` ms (`-478.15594748438644` ms, `3.4804x` faster).
- Baseline `elapsed_ms_mean`: `11.469601104701203`, `11.83402184064367`, `11.376669148116239` ms; mean `11.560097364487038` ms.
- Post-change `elapsed_ms_mean`: `11.328100160296474`, `11.209248282414462`, `11.837638997738916` ms; mean `11.458329146816617` ms (`-0.10176821767042154` ms, within noise but favorable).
- Baseline `update_channel_elapsed_ms_mean`: `77.71662601070213`, `73.00600903441331`, `78.2674318678411` ms; mean `76.33002230431884` ms.
- Post-change `update_channel_elapsed_ms_mean`: `72.1716888282182`, `76.26023690681905`, `77.38882556025472` ms; mean `75.27358376509732` ms (`-1.0564385392215263` ms, within noise but favorable).
- Baseline `product_version_peak_bytes_mean`: `2200.5714285714284` bytes across all three runs.
- Post-change `product_version_peak_bytes_mean`: `1404.142857142857` bytes across all three runs (`-796.4285714285713` bytes).

Decision: accepted because the targeted registered product-version submetric
improved substantially across the local Linux probe triplet, memory moved lower,
and unrelated registered metrics stayed within the warning boundary.
