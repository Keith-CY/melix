# Evaluation text heuristic strip elision

## Scope

This Python-only performance slice is limited to `services/mlx-worker-python/worker/productization/evaluation_final_result.py` and the text `heuristic_final` extraction path.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `evaluation-final-result-text-fallback-tail-scan` in `infra/perf/pr_scoped_probes.json`. The existing registry entry provides focused `test_command`, `coverage_command`, and `probe_command` entries for the production path, focused final-result tests, PR-scoped performance selection tests, and `scripts/evaluation_text_fallback_probe.py`.

## Change

The text heuristic path no longer strips the full raw response before dispatching to `_extract_text_heuristic(...)`. It now performs an empty/whitespace-only guard and lets the existing answer-prefix, fence, and tail-line extraction helpers normalize only the selected candidate. Strict full-response extraction and JSON heuristic extraction keep the previous full-response strip behavior.

This preserves whitespace-wrapped text answers while avoiding one large string allocation and full-buffer copy on the common long text fallback path.

## Validation plan

1. Run the focused final-result regression tests and PR-scoped probe selection tests from the registered probe command.
2. Run the registered changed-scope coverage command for `evaluation-final-result-text-fallback-tail-scan` and keep changed-scope coverage at or above 95%.
3. Run the registered local Linux probe for `evaluation-final-result-text-fallback-tail-scan` and accept only if the text fallback metrics show a clear improvement without behavior drift.
4. Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.
