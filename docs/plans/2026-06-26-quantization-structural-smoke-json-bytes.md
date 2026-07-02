# Quantization structural smoke JSON byte-read slice

## Scope

This Python-only performance slice is limited to the structural smoke-test JSON
validation path in `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`.
The hot path runs when quantization requests ask for local smoke validation, and
it validates `config.json` and `tokenizer.json` before recording smoke evidence.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`model-ops-bundle-artifact-byte-accounting` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and its `phase5_model_ops_metrics.py` workload runs the
quantize operation with `run_smoke_test=True`, so this structural smoke path is
exercised in local and CI performance evidence.

## Optimization

Keep structural smoke behavior unchanged while replacing the intermediate text
read/decode allocation with `Path.read_bytes()` passed directly to `json.loads()`.
Malformed JSON, missing files, and successful validation keep the same evidence
shape and failure messaging.

## Verification plan

1. Add a focused regression test proving structural smoke validation reads JSON
   through bytes and still reports invalid JSON failures.
2. Run the registered focused test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally against `origin/main` and this branch.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Linux validation boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime
behavior changes are included.
