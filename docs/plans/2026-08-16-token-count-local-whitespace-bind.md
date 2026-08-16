# Token count local whitespace binding

## Scope

This Python-only performance slice is limited to the shared deterministic
`worker.runtime.token_counting.whitespace_token_count` helper used by the OCR,
VLM, and vision-family deterministic token estimators. The affected path is
already covered by the registered PR-scoped `deterministic-vlm-completion-token-scan`
probe, whose watch globs include `services/mlx-worker-python/worker/runtime/token_counting.py`
and whose focused test, coverage, and probe commands are declared in
`infra/perf/pr_scoped_probes.json`.

## Plan

1. Preserve the existing split-compatible whitespace token counting semantics for
   ASCII and non-ASCII text.
2. Keep the current allocation-avoiding scanner and make only the smallest hot
   loop improvement: bind the ASCII whitespace lookup table to a local variable
   before scanning.
3. Verify with the focused deterministic VLM/token-count tests, changed-scope
   coverage, and the registered deterministic VLM completion token probe.

## Metrics

Expected direction: lower `elapsed_ms_mean` for
`scripts/deterministic_vlm_completion_token_probe.py` with unchanged
`completion_tokens`, `token_count_calls_mean`, and prompt-count behavior.

The Linux-local probe validates the Python helper behavior and timing. Swift or
macOS runtime effects are outside this slice.
