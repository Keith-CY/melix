# Deterministic OCR Token Count Local Arithmetic Slice

## Scope

Optimize the deterministic OCR prompt token-count hot path without changing
reported token counts. The slice is limited to
`DeterministicOCRRuntime.prompt_token_count()` and its focused regression
coverage.

## Probe

Registered PR-scoped probe:
`deterministic-ocr-token-count-scan` in
`infra/perf/pr_scoped_probes.json`.

The registered probe provides:

- `test_command` for OCR token-count and PR-scoped performance selection tests.
- `coverage_command` for changed-scope coverage on the touched OCR/probe files.
- `probe_command` for repeated local Linux timing of
  `scripts/deterministic_ocr_token_count_probe.py`.

## Implementation Plan

1. Preserve the existing whitespace token-count helper behavior.
2. Keep the single-image OCR fast path on precomputed
   `preprocess_input_bytes` so it does not read image byte lengths.
3. Remove redundant outer `max(1, ...)` work once an image-token minimum has
   already been applied.
4. Keep the zero-image fallback clamped to at least one token.
5. Verify focused tests, changed-scope coverage, and the registered probe before
   opening the PR.

## Local Evidence

Baseline from `origin/main`:

```json
{"checksum": 80000000.0, "elapsed_ms_mean": 248.70167, "iterations": 80000.0, "peak_bytes_mean": 163.2, "sample_count": 5.0, "token_count": 200.0}
```

Candidate branch:

```json
{"checksum": 80000000.0, "elapsed_ms_mean": 147.018257, "iterations": 80000.0, "peak_bytes_mean": 147.2, "sample_count": 5.0, "token_count": 200.0}
```

Local delta: -101.683413 ms mean, about 40.9% lower elapsed time for the
registered probe workload; peak traced bytes decreased from 163.2 to 147.2.
