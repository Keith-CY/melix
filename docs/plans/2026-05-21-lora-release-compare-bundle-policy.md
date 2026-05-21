# LoRA Release Compare Bundle Policy

## Goal

Implement issue #726 by making every LoRA adapter manifest able to declare the
compare evidence bundle required before an adapter is published or promoted.

Parent direction: issue #724, "OpenSearch-VL alignment: gate LoRA release with
paired compare evidence".

## Scope

This slice adds an additive adapter-manifest contract only:

- in-domain evaluation suite IDs that must improve for the adapter's intended
  domain
- guard suite IDs that must not regress on general behavior
- per-suite effect thresholds
- per-suite minimum paired sample counts

Out of scope:

- automatically launching compare jobs after training
- enforcing release-gate verdicts
- adding new Swift, protobuf, or menu bar fields
- changing existing `eval compare` scoring semantics

## Manifest Contract

`train_lora.adapter.json` keeps schema `melix.lora_adapter_package.v1` and adds
`release_compare_bundle_policy`:

```json
{
  "schema_version": "melix.lora_release_compare_bundle_policy.v1",
  "in_domain_suite_ids": ["opensearch_vl_qa"],
  "guard_suite_ids": ["mmlu", "gsm8k"],
  "thresholds": {
    "opensearch_vl_qa": 0.05,
    "mmlu": 0.01,
    "gsm8k": 0.01
  },
  "minimum_sample_counts": {
    "opensearch_vl_qa": 80,
    "mmlu": 40,
    "gsm8k": 40
  }
}
```

The adapter manifest also exposes the same values through flat
`release_compare_*` keys for registry snapshots, reports, and future release
gate readers that avoid nested JSON traversal.

## Operator Inputs

The existing `train_lora` `ext` map accepts these additive keys:

- `release_compare_in_domain_suite_ids`: comma-separated suite IDs
- `release_compare_guard_suite_ids`: comma-separated suite IDs
- `release_compare_thresholds`: comma-separated `suite_id=value` entries
- `release_compare_default_threshold`: optional threshold applied to suites
  without an explicit threshold
- `release_compare_minimum_sample_counts`: comma-separated `suite_id=value`
  entries
- `release_compare_default_minimum_sample_count`: optional minimum applied to
  suites without an explicit minimum

The equivalent namespaced `melix.release_compare.*` keys are accepted for
callers that already group ext fields by domain.

## Validation

- suite lists are de-duplicated while preserving order
- threshold values must be numeric and `>= 0.0`
- minimum sample counts must be integers and `>= 1`
- empty policy fields remain valid so older training callers keep producing
  backward-compatible manifests

## Performance And Metrics

This path only parses a handful of request strings and writes JSON fields during
the offline `train_lora` manifest step. It adds no serving-path work and no
compare execution work.

Measurement points:

- focused pytest runtime for LoRA training config and manifest persistence
- changed-scope coverage for the Python files touched by this contract and the
  relevant performance-probe coverage commands
- `git diff --check`

Success metrics:

- focused LoRA tests pass
- changed-scope coverage for touched Python files is at least 95%
- generated adapter manifest records nested and flat release compare policy
  fields

## Implementation Plan

- [x] Add a normalized release compare bundle policy to `LoRATrainingConfig`.
- [x] Persist the normalized policy in `train_lora.adapter.json`.
- [x] Document the operator ext keys in the LoRA adapter workflow runbook.
- [x] Add focused tests for parsing, validation, and manifest persistence.
- [x] Run focused pytest, changed-scope coverage, and `git diff --check`.

## Verification

- `python3 -m py_compile services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/model_ops/release_compare_policy.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/tests/test_release_compare_policy.py`
  - Result: passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_release_compare_policy.py`
  - Result: 6 passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/lora_release_compare_policy.coverage -m pytest -q services/mlx-worker-python/tests/test_release_compare_policy.py && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage json --data-file=/tmp/lora_release_compare_policy.coverage -o /tmp/lora_release_compare_policy_coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json /tmp/lora_release_compare_policy_coverage.json services/mlx-worker-python/worker/model_ops/training_config.py services/mlx-worker-python/worker/model_ops/release_compare_policy.py services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py services/mlx-worker-python/tests/test_release_compare_policy.py`
  - Result: 6 passed; changed-line coverage 100% (117/117).
- `python3 - <<'PY' ... pre_commit_gate.run_performance_report(...)`
  - Result: Status ok; selected 2 direct probes
    (`training-config-target-module-cache` and
    `lora-reward-summary-candidate-minmax`); targeted tests passed; probe
    coverage passed at 100%; no verification failures and no regressions.
- `git diff --check`
  - Result: passed.

## Known Gaps

Milestone 2 will consume this contract to automate base-versus-adapter compare
execution. Milestone 3 will enforce the persisted verdicts in release gates.
