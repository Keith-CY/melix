# Engine empty stop sequence fast path

## Scope

This Python performance slice targets `EngineCore._sampling_with_resolved_stop()` in `services/mlx-worker-python/worker/engine/engine_core.py`.

The generate hot path resolves sampling stop sequences for every request. Most deterministic and probe requests carry no explicit stop strings and no runtime-resolved stop sequences, so the helper can return the original `SamplingConfig` before materializing `tuple(sampling.stop)`.

## Registered probe

The affected path is covered by the existing PR-scoped `engine-generate-usage-token-elision` probe in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` values for the generate engine path, the focused unit tests, and `scripts/engine_generate_usage_token_probe.py`.

## Implementation plan

1. Preserve the existing identity behavior when the incoming sampling stops and resolved stop sequence are both empty.
2. Add a direct empty/empty branch before tuple materialization.
3. Keep all non-empty and changed-stop behavior unchanged.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the registered probe locally on Linux. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.

## Environment boundary

This slice is Python-only and locally verifiable on Linux. No Swift runtime performance claim is made.
