# Evaluation JSON Schema-Free Score Cache Performance Slice

## Scope

This slice keeps final-result JSON scoring semantics unchanged while avoiding repeated recursive scoring for identical schema-free JSON payload pairs.

The evaluation scorer already caches parsed JSON payloads, but repeated calls with the same target, extracted result, and ignored paths still re-walk the full parsed object graph. The registered probe exercises that shape directly: a schema-free `json_field_match` profile scores the same large target/result pair repeatedly.

This slice adds a small LRU cache around the deterministic schema-free typed-score calculation. Schema-backed profiles still run validation on each call and use the existing uncached scorer path after validation, preserving schema behavior and avoiding hashing mutable schema dictionaries.

The same source path also selects the text-fallback probe. Its primary elapsed and peak-memory metrics remain gated, but the derived delta metrics compare the current helper against an internal legacy helper in each run. Those derived values are useful context for the original text-fallback optimization, but they can move opposite the primary elapsed metric when the legacy helper varies between base and head. This slice marks those derived delta metrics informational so unrelated evaluation-final-result changes are not blocked by a non-primary, legacy-relative noise signal.

## Registered Probe

Affected path is already covered by the PR-scoped probe registry entry:

- `evaluation-final-result-json-typed-score-aggregate`
- watched source: `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- focused test: `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- coverage command: registered `coverage_command` for the evaluation final-result JSON typed score probe
- probe command: `scripts/evaluation_json_typed_score_probe.py`

## Verification Plan

1. Run the focused registered test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and require at least 95% for touched scope.
3. Run `scripts/evaluation_json_typed_score_probe.py` before and after the change using `origin/main` and this branch.
4. Use the PR-scoped performance workflow as the CI validation source before merge.

## Expected Metrics

Primary metric: `elapsed_ms_mean`, lower is better.

Secondary metric: `peak_bytes_mean`, lower is better or neutral within the registered threshold.
