# Serving diagnostics JSON literal byte cache slice

## Scope

This Python-only performance slice targets the serving diagnostics JSONL fast path in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

The affected path is covered by the registered PR-scoped probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries for the serving diagnostics implementation, tests, and `scripts/serving_diagnostics_queue_probe.py`.

## Optimization

Keep the existing string JSON literal cache for call sites that need `str`, and add a paired cached byte-literal helper for JSONL serialization. The writer and direct event helper now reuse cached UTF-8 bytes for request IDs, phases, and statuses instead of taking a cached string literal and encoding it again on every miss or generic fast-path row.

This preserves the existing compact, sorted JSON field order and all fallback behavior while avoiding repeated `str.encode("utf-8")` work in the debug queue serialization path.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime performance claims are made.

## Verification plan

1. Run the registered focused `test_command` for `serving-diagnostics-debug-queue-bounds`.
2. Run the registered changed-scope `coverage_command` and require at least 95% coverage for touched scope.
3. Run the registered `probe_command` locally on Linux against `origin/main` and this branch and compare `serialization_elapsed_ms_mean`.
4. Require the PR-scoped performance workflow to run the registered probe in CI before merge.
