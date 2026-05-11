# Code Evaluation Nonblank Line Counter Allocation Slice

## Scope

This Python performance slice is limited to the fallback test-counting path in `services/mlx-worker-python/worker/engine/code_eval_runner.py` when syntax-error or no-assert test payloads require counting nonblank lines.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `code-eval-test-count-nonblank-streaming` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and measures peak traced allocation while preserving the expected nonblank-line count.

## Optimization

Replace the regular-expression `finditer` count with a streaming character scan that counts a line once when the first non-whitespace character is seen. This avoids regex match object allocation on large fallback test payloads while preserving `splitlines`-compatible nonblank-line semantics for spaces, tabs, `\n`, and `\r\n` inputs.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate.

## Success Metrics

- Focused code-eval tests pass.
- Changed executable line coverage for touched Python scope is at least 95%.
- The registered `code-eval-test-count-nonblank-streaming` probe preserves `nonblank_line_count_mean=48000` and lowers `peak_bytes_mean` versus the origin/main baseline samples. The probe's elapsed metric is informational for this slice.
