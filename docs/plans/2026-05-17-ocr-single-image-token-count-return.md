# OCR Single-image Token Count Return Slice

## Goal

Trim the deterministic OCR prompt token-count hot path for the common single-image
request by returning immediately after combining prompt tokens with the precomputed
image input byte count.

## Scope

- `services/mlx-worker-python/worker/runtime/deterministic_ocr_runtime.py`
- Existing focused OCR token-count tests in `services/mlx-worker-python/tests/test_vision_runtime.py`
- Existing PR-scoped probe `deterministic-ocr-token-count-scan`

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`deterministic-ocr-token-count-scan` in `infra/perf/pr_scoped_probes.json`. The
entry includes focused `test_command`, `coverage_command`, and `probe_command`
values for the deterministic OCR token-count workload.

## Plan

1. Keep token-count semantics unchanged for single-image and multi-image OCR
   requests.
2. Avoid assigning an intermediate `image_tokens` variable on the common
   single-image path and return the final bounded total directly.
3. Run the registered focused tests, changed-scope coverage, and local registered
   probe on Linux before opening the PR.
4. Use the GitHub PR-scoped performance workflow as the final base-vs-head gate.

## Validation boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
performance claim is made.
