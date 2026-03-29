# M6.11 Quantization Benchmark And Regression Gates

## Goal

Close the quantization milestone with benchmark evidence and regression gates that protect quality, throughput, and artifact correctness.

## Scope

- add benchmark evidence for quantized artifacts
- add regression thresholds and structured failure behavior
- keep gate outputs discoverable from release automation

## Files

- update `services/mlx-worker-python/worker/productization/`
- update `scripts/`
- update `infra/release/`
- update `docs/runbooks/`

## Implementation Notes

- gate inputs should remain machine-readable and repository-owned
- compare quantized outputs against baseline artifacts and serving behavior
- keep experimental acceleration metrics separable from base quantization metrics

## Verification

- touched-scope benchmark command for quantization
- touched-scope release-gate command for quantization regressions

## Acceptance

- quantized artifacts have benchmark evidence and regression thresholds
- release automation can fail closed on quantization regressions
