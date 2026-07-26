# Job registry removed-target tuple slice

## Scope

This Python-only slice narrows `worker.model_ops.job_registry.ModelOpsJobRegistry` active derived-model row construction. The removed-target scan previously returned a short-lived dictionary of sets and the active-row builder immediately indexed that dictionary by string keys. The new slice returns the four removed-target sets as a fixed tuple and unpacks them at the single call site.

Behavior remains unchanged:

- completed `remove_derived_model` jobs still suppress matching derived-model IDs, activation manifest paths, adapter manifest paths, and activation job IDs;
- active derived-model row caching and invalidation remain unchanged;
- target resolution by model ID and manifest path still returns copied payloads.

## Registered probe

The affected path is covered by the PR-scoped registered probe `job-registry-derived-model-single-pass` in `infra/perf/pr_scoped_probes.json`. The probe watches `services/mlx-worker-python/worker/model_ops/job_registry.py`, includes focused `test_command`, `coverage_command`, and `probe_command` entries, and reports active manifest lookup, target resolution, manifest-path resolution, and restore elapsed metrics.

## Implementation plan

1. Reuse existing active derived-model cache/removal tests for behavior parity.
2. Replace the internal removed-target dictionary return value with a fixed tuple.
3. Keep the returned set contents and all cache invalidation behavior unchanged.
4. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux. Use the PR-scoped performance workflow as the CI validation source after push.

## Baseline and local probe evidence

Local Linux registered probe before the change, three runs:

```json
{"active_manifest_elapsed_ms_mean": 0.000539, "elapsed_ms_mean": 35.884745, "manifest_path_elapsed_ms_mean": 0.000942, "resolve_target_elapsed_ms_mean": 0.001015, "resolve_trimmed_target_elapsed_ms_mean": 0.00138, "restore_elapsed_ms_mean": 35.880868}
{"active_manifest_elapsed_ms_mean": 0.000383, "elapsed_ms_mean": 40.240627, "manifest_path_elapsed_ms_mean": 0.000893, "resolve_target_elapsed_ms_mean": 0.000817, "resolve_trimmed_target_elapsed_ms_mean": 0.001815, "restore_elapsed_ms_mean": 40.23672}
{"active_manifest_elapsed_ms_mean": 0.000578, "elapsed_ms_mean": 37.302682, "manifest_path_elapsed_ms_mean": 0.000953, "resolve_target_elapsed_ms_mean": 0.001072, "resolve_trimmed_target_elapsed_ms_mean": 0.001455, "restore_elapsed_ms_mean": 37.298624}
```

Local Linux registered probe after the change, three runs:

```json
{"active_manifest_elapsed_ms_mean": 0.000432, "elapsed_ms_mean": 36.486559, "manifest_path_elapsed_ms_mean": 0.000908, "resolve_target_elapsed_ms_mean": 0.000878, "resolve_trimmed_target_elapsed_ms_mean": 0.001224, "restore_elapsed_ms_mean": 36.483116}
{"active_manifest_elapsed_ms_mean": 0.00053, "elapsed_ms_mean": 34.91051, "manifest_path_elapsed_ms_mean": 0.000885, "resolve_target_elapsed_ms_mean": 0.001023, "resolve_trimmed_target_elapsed_ms_mean": 0.002014, "restore_elapsed_ms_mean": 34.906058}
{"active_manifest_elapsed_ms_mean": 0.000429, "elapsed_ms_mean": 38.941331, "manifest_path_elapsed_ms_mean": 0.000801, "resolve_target_elapsed_ms_mean": 0.000951, "resolve_trimmed_target_elapsed_ms_mean": 0.001247, "restore_elapsed_ms_mean": 38.937902}
```

Three-run mean comparison:

- baseline `elapsed_ms_mean`: `37.809351 ms`
- tuple-return `elapsed_ms_mean`: `36.779467 ms`
- delta: `-1.029884 ms` (`2.72%` faster)
- baseline `restore_elapsed_ms_mean`: `37.805404 ms`
- tuple-return `restore_elapsed_ms_mean`: `36.775692 ms`
- delta: `-1.029712 ms` (`2.72%` faster)

## Success criteria

- Focused job-registry tests pass.
- Changed-scope coverage for the touched runtime utility, tests, and probe paths is at least 95%.
- The registered probe keeps active derived-model counts unchanged and shows no registered metric regression in CI.
