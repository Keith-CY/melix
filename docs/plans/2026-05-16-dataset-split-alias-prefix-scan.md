# Dataset split alias prefix scan optimization

## Scope

This Python-only performance slice is limited to split/config inference in
`services/mlx-worker-python/worker/dataset_registry/catalog.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-snapshot-inference-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries for the catalog implementation,
dataset registry tests, PR-scoped performance selection tests, and
`scripts/dataset_registry_snapshot_probe.py`.

## Change

`_split_alias_from_candidate(...)` now finds the first `-` or `_` delimiter with
string scans instead of creating two temporary split lists. This keeps the legacy
prefix semantics for split names such as `train-00000`, `validation_00000`, and
mixed delimiter names while reducing per-file allocations in snapshot inference.

The same slice also normalizes this registered probe's `coverage_command` and
`probe_command` from `python` to `python3` so the CI and local evidence path uses
the repository-required interpreter spelling. This does not change probe
semantics.

## Validation plan

1. Run the focused dataset registry tests plus the registered probe-selection and
   probe smoke tests.
2. Run changed-scope coverage for the catalog/test/probe files.
3. Run the registered probe locally on Linux with repeated samples against this
   branch and compare with the `origin/main` baseline collected before the edit.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Local baseline

Baseline before implementation on `origin/main` (`8c78df16`) with
`MELIX_DATASET_REGISTRY_PROBE_SAMPLES=7`:

- `elapsed_ms_mean=689.901475`
- `peak_bytes_mean=870990.285714`
- `legacy_inference_helper_calls_mean=0.0`
- `file_count_mean=2401.0`

## Local registered probe result

Registered probe runner after implementation with `MELIX_DATASET_REGISTRY_PROBE_SAMPLES=7`:

- base (`origin/main`, `8c78df16`): `elapsed_ms_mean=719.119751`,
  `peak_bytes_mean=872607.857143`
- head: `elapsed_ms_mean=673.583747`, `peak_bytes_mean=872599.428571`
- elapsed delta: `-45.536003 ms` (`-6.33%`)
- parity guards unchanged: `legacy_inference_helper_calls_mean=0.0`,
  `file_count_mean=2401.0`
- changed-scope coverage from the registered command: `100%`
