# Runtime utils top-level weight streaming

## Scope

This Python-only slice narrows `worker.runtime.runtime_utils._top_level_weight_file_bytes()`.
Flat local model bundles without a valid `model.safetensors.index.json` still need the same
resident-byte estimate, but the fallback scan no longer needs to materialize the full
`Path.iterdir()` result before measuring each top-level candidate.

## Registered probe

Register `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`.
The probe builds a synthetic flat model bundle and repeatedly calls
`estimate_model_weight_resident_bytes(...)`. It reports:

- `elapsed_ms_mean` (`lower_is_better`)
- `peak_bytes_mean` (`lower_is_better`)
- workload guard rails: `file_count`, `iterations`, `expected_bytes`, and `checksum`

The focused test and coverage commands cover the runtime utility behavior, PR-scoped probe
selection, and the probe script smoke test.

## Verification plan

- Run the focused runtime-utils pytest selection.
- Run changed-scope coverage for the touched runtime utility, tests, and probe script.
- Run the registered probe locally on Linux and compare against `origin/main` before opening the PR.
- Use the PR-scoped performance workflow as the merge gate after push.

## Acceptance

- Behavior remains unchanged for indexed bundles, flat bundles, missing paths, and stat/list errors.
- `_top_level_weight_file_bytes()` streams `Path.iterdir()` entries instead of materializing a tuple.
- Local registered probe shows lower peak allocation and no worse resident-byte guard rails.

## 2026-05-23 suffix prefilter slice

The follow-up Python slice keeps the same registered probe and narrows only the
model-weight filename classification hot path. `_is_model_weight_filename(...)`
now rejects names whose final character cannot match any supported model-weight
suffix before running tuple `endswith(...)`, `islower()`, or lowercase fallback
work. This preserves existing case-sensitive and case-insensitive suffix behavior
while avoiding extra string checks for common non-weight files in flat bundles.

Validation remains the focused runtime-utils pytest selection, changed-scope
coverage for `runtime_utils.py`, `test_runtime_utils.py`, and the registered probe
script, plus the local and CI `runtime-utils-top-level-weight-streaming` probe.
