# Token count probe raw helper fast path

## Scope

This Python-only performance slice is limited to the registered deterministic OCR token-count probe script:

- `scripts/deterministic_ocr_token_count_probe.py`

It does not change runtime token-counting behavior. The slice improves OCR probe fidelity and local/CI probe throughput by bypassing the shared `whitespace_token_count` LRU wrapper through its `__wrapped__` raw helper instead of calling `cache_clear()` inside the measured helper loop. A matching VLM probe edit was measured locally and rejected because it did not improve the VLM probe workload.

## Registered probes

The affected script is already covered by a registered PR-scoped probe in `infra/perf/pr_scoped_probes.json` with focused `test_command`, `coverage_command`, and `probe_command` entries:

- `deterministic-ocr-token-count-scan`

The entry watches the OCR probe script and the shared token-counting runtime tests, so PR-scoped performance CI remains the merge gate for this slice.

## Plan

1. Bind the undecorated whitespace token-count helper once in the OCR probe script.
2. Replace per-iteration `cache_clear()` calls with direct raw-helper calls for the synthetic raw-count workload.
3. Add focused regression coverage that fails if the OCR probe script clears the shared LRU cache during execution.
4. Run focused tests, changed-scope coverage, and the registered OCR probe locally on Linux before opening the PR.

## Acceptance

- Focused behavior tests pass locally.
- Changed-scope coverage for the touched probe scripts and focused tests is at least 95%.
- The registered local OCR probe reports lower elapsed time for the probe workload compared with the `origin/main` baseline.
- GitHub Actions and the PR-scoped performance report complete successfully before merge.