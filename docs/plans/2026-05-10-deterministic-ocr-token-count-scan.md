# Deterministic OCR token count scan slice

## Scope

Optimize `services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py` token accounting by replacing `str.split()` list materialization with a small cached whitespace scanner for OCR prompt and completion token counts.

## Performance probe

This slice registers `deterministic-ocr-token-count-scan` in `infra/perf/pr_scoped_probes.json` with focused:

- `test_command` for OCR behavior, registry selection, and probe smoke coverage.
- `coverage_command` for changed-scope coverage over the OCR runtime, focused tests, probe registry tests, and the probe script.
- `probe_command` via `scripts/deterministic_ocr_token_count_probe.py`, reporting `elapsed_ms_mean` and `peak_bytes_mean` for repeated OCR prompt-token accounting.

## Verification boundary

This is a Python runtime slice and is locally verifiable on Linux. The PR-scoped performance workflow is still required before merge so the registered probe runs under CI with the changed scope.

## Success criteria

- OCR token counts remain equivalent to Python whitespace splitting for prompt and completion accounting.
- Changed-scope coverage remains at least 95%.
- The registered probe shows a lower `elapsed_ms_mean` than the origin/main baseline, or a clearly bounded non-regression.
