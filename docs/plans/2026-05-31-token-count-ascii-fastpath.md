# Token count ASCII whitespace fast path

## Scope

This Python-only performance slice is limited to `worker.runtime.token_counting.whitespace_token_count()` and its existing deterministic vision callers. The helper remains the shared token-counting implementation for deterministic OCR/VLM usage metrics.

## Registered probes

The affected helper is already covered by registered PR-scoped probes in `infra/perf/pr_scoped_probes.json` with focused `test_command`, `coverage_command`, and `probe_command` entries:

- `deterministic-ocr-token-count-scan`
- `deterministic-vlm-completion-token-scan`

Both probes watch `services/mlx-worker-python/worker/runtime/token_counting.py` plus their focused tests and probe scripts. The OCR probe is used as the primary local Linux probe for this slice; CI remains the repository merge gate and will run the registered PR-scoped performance workflow for the changed scope.

## Plan

1. Preserve the non-allocating single-pass token counter semantics.
2. Add an ASCII-only whitespace membership fast path using the exact ASCII whitespace set recognized by `str.split()`/`str.isspace()` for ASCII text.
3. Keep the existing Unicode fallback path through `str.isspace()` so non-ASCII whitespace semantics are unchanged.
4. Add regression coverage for ASCII vertical-tab/form-feed whitespace and non-ASCII Unicode whitespace.
5. Run focused OCR/VLM token-count tests, changed-scope coverage, and the registered OCR/VLM probes locally on Linux before opening the PR.

## Acceptance

- Focused behavior tests pass locally.
- Changed-scope coverage for `token_counting.py` and touched tests is at least 95%.
- Registered local probes report directionally lower elapsed time for the ASCII-heavy synthetic token-count workload.
- GitHub Actions and the PR-scoped performance report complete successfully before merge.
