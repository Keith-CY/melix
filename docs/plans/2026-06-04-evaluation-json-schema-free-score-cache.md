# Evaluation JSON schema-free score cache

## Scope

This performance slice targets the schema-free JSON final-result scoring hot path in
`worker.productization.evaluation_final_result.score_final_result`.

## Registered probe

The affected path is already covered by the PR-scoped probe
`evaluation-final-result-json-typed-score-aggregate` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- `scripts/evaluation_json_typed_score_probe.py`

## Optimization hypothesis

Repeated schema-free JSON scoring currently caches the parsed payloads and the
computed float score, but every call still performs cache lookups, rounds the
score, and constructs a new `ScoringOutcome`. Cache the immutable validated
`ScoringOutcome` for schema-free scoring so repeated identical evaluation rows
can reuse the full result object while preserving invalid-target and
invalid-extracted JSON behavior.

## Verification plan

1. Run the focused evaluation final-result tests from the registered probe.
2. Run changed-scope coverage from the registered probe and require at least 95%.
3. Run `scripts/evaluation_json_typed_score_probe.py` locally on Linux before and
after the implementation and compare `elapsed_ms_mean`.
4. Let the PR-scoped performance GitHub Action validate the registered probe in CI.
