# Code Evaluation Nonblank Line Counter Allocation Slice

## Scope

This Python performance slice is limited to the fallback test-counting path in `services/mlx-worker-python/worker/engine/code_eval_runner.py` when syntax-error or no-assert test payloads require counting nonblank lines.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `code-eval-test-count-nonblank-streaming` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and measures peak traced allocation while preserving the expected nonblank-line count.

## Optimization

Replace the regular-expression `finditer` count with a streaming character scan that counts a line once when the first non-whitespace character is seen. This avoids regex match object allocation on large fallback test payloads while preserving `splitlines`-compatible nonblank-line semantics for Python line boundaries including LF, CRLF/CR, VT, FF, file/group/record separators, NEL, LS, and PS.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate.

## Success Metrics

- Focused code-eval tests pass.
- Changed executable line coverage for touched Python scope is at least 95%.
- The registered `code-eval-test-count-nonblank-streaming` probe preserves `nonblank_line_count_mean=48000` and lowers `peak_bytes_mean` versus the origin/main baseline samples. The probe's elapsed metric is informational for this slice.

## 2026-05-31 Implementation Note

The registered probe coverage command now includes the splitlines-semantics test so
all Python line boundary branches remain measured by changed-scope coverage after
review follow-up. Local Linux base-vs-head probe evidence showed the streaming
counter kept `nonblank_line_count_mean=48000` while reducing `peak_bytes_mean`
from `2117.0` to `112.0` bytes; `elapsed_ms_mean` increased from `45.36` to
`77.21` ms and remains informational for this allocation-focused slice.

## 2026-06-03 ASCII Fast Path Follow-up

This follow-up keeps the same registered probe and narrows the implementation to
the large-payload `_count_nonblank_test_lines` fallback. Common executable-code
evaluation test payloads are ASCII, so the counter now detects ASCII payloads and
uses ASCII-only splitline and whitespace membership checks. Non-ASCII payloads
continue through the existing Unicode splitline-compatible path, preserving the
documented LF, CR/CRLF, VT, FF, file/group/record separator, NEL, LS, and PS
semantics.
