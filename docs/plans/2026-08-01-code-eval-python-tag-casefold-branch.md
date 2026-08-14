# Code evaluation Python fence tag case branch

## Scope

This Python-only performance slice is limited to `worker/engine/code_eval_runner.py`, specifically the case-insensitive `python` code-fence tag check used by `extract_candidate_code()`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `code-eval-code-block-last-match-streaming` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_code_block_extract_probe.py`

## Optimization slice

The case-insensitive Python fence helper now checks each character with direct equality branches instead of one-character membership tests. Exact lowercase `python` fences still use the existing `str.startswith()` fast path; this slice targets mixed-case Python fences in repeated code-block extraction without changing handling for unknown language tags.

This follow-up slice remains within the same registered code-block extraction probe and narrows the trailing-strip helper used after a fenced block is selected. ASCII tail whitespace now uses a precomputed ordinal lookup, while non-ASCII tail characters still fall back to `str.isspace()` so Unicode whitespace trimming semantics remain unchanged. The probe's main extraction workload exercises the common single trailing newline before the closing fence; behavior parity is guarded by the focused extraction test, including Unicode whitespace.

This 2026-08-02 follow-up slice stays in the same registered code-block extraction probe and applies the same ASCII whitespace lookup pattern to the leading content-start skip after a code fence tag. The common ASCII whitespace prefix now avoids repeated `str.isspace()` calls while non-ASCII leading whitespace still falls back to Unicode `str.isspace()` semantics. Focused extraction tests cover ASCII and Unicode leading whitespace after the `python` tag.

This 2026-08-14 follow-up keeps the same behavior and registered probe while moving the code-block whitespace lookup table and `ord` builtin bindings onto `_stripped_slice()` and `_code_block_content_start()` defaults. That removes two per-call local rebinding steps from repeated fenced-code extraction without changing ASCII or Unicode whitespace handling.

## Verification plan

Run the focused registered test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
