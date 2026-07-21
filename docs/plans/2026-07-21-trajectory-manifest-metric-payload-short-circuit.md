# Trajectory Manifest Metric Payload Short-Circuit

This Python-only performance slice stays limited to `worker.trajectory_provenance.load_trajectory_provenance_from_snapshot_manifest()` for normalized agentic trajectory snapshot manifests loaded from JSON bytes.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `trajectory-manifest-json-load` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/trajectory_provenance.py`
- `services/mlx-worker-python/tests/test_trajectory_provenance.py`
- `scripts/trajectory_manifest_json_load_probe.py`

## Slice

Common probe and training manifests contain only the required identity fields plus `trajectory_quality_metrics` and `agentic_sft_token_metrics`, with schema and split defaulted. Once the loader has validated those required fields, it can return this metric-only shape directly instead of probing each optional provenance field that is absent in the hot payload.

The fallback path remains unchanged for manifests with optional toolset, registry, policy, leakage, package, explicit schema, explicit split, malformed text, or mapping-subclass inputs.

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and `trajectory-manifest-json-load` probe locally on Linux before opening the PR. The probe compares the slow compatibility baseline with the optimized loader and records elapsed time plus peak allocation metrics.
