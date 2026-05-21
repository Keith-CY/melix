# Code Evaluation JSON Bounds Fast Path

## Scope

This Python-only performance slice is limited to the code-evaluation payload fast path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

## Goal

Avoid byte-by-byte leading/trailing whitespace scans when `_load_payload_file()` receives the common compact JSON object payload emitted by the sandbox runner or by sorted-key probe fixtures. Payloads whose first byte is `{` and final byte is `}` can return object bounds immediately; payloads with surrounding whitespace or malformed delimiters keep the existing validation path.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json` with focused `test_command`, `coverage_command`, and `probe_command` entries.

## Linux validation boundary

This slice is entirely Python and locally verifiable on Linux. No Swift runtime behavior is changed.

## Success metrics

- Focused code-eval tests and PR-scoped probe registry tests pass.
- Changed-scope coverage for touched executable Python scope remains at least 95%.
- `scripts/code_eval_payload_json_probe.py` reports lower `elapsed_ms_mean` with unchanged payload size and peak memory.
