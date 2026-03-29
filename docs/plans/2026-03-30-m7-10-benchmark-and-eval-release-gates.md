# M7.10 Benchmark And Eval Release Gates

## Goal

Feed benchmark and evaluation outputs into release-gate automation so model-quality and serving-regression evidence are part of release acceptance.

## Scope

- extend release gates with benchmark and evaluation signals
- preserve repository-owned policy thresholds
- keep gate outputs machine-readable

## Files

- update `services/mlx-worker-python/worker/productization/release_gates.py`
- update `infra/release/`
- update `scripts/`
- update `docs/runbooks/`

## Implementation Notes

- gate policy should distinguish serving regression from evaluation regression
- gate failures should remain explicit and reproducible
- use repository-owned benchmark and evaluation artifacts rather than hidden external checks

## Verification

- touched-scope release-gate command for benchmark and eval signals
- `make py-test`

## Acceptance

- release gates can fail closed on benchmark or evaluation regressions
- benchmark and evaluation evidence are first-class release inputs
