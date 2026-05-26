# Native MTP weight-key type fast path

## Scope

This Python-only slice narrows `worker.runtime.native_mtp.mlx_lm_loader._is_mtp_weight_key()` inside the registered native-MTP loader sidecar scan path. Native safetensor index `weight_map` keys are checked repeatedly while filtering sidecar MTP shards, so the hot path now uses one tuple-prefix `startswith()` call instead of two separate prefix checks while preserving the same `str(key)` fallback behavior for custom/non-string mapping keys.

## Probe

Registered PR-scoped probe: `native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.

The affected path is covered by focused `test_command`, `coverage_command`, and `probe_command` entries. This slice extends the registered probe with a dedicated key-prefix predicate measurement (`key_old_mean_ms`, `key_new_mean_ms`, `key_delta_ms`, `key_speedup`) in addition to the existing sidecar scan metrics (`extra_old_mean_ms`, `extra_new_mean_ms`, `extra_delta_ms`, `extra_speedup`) for `extra_mtp_safetensor_files()`.

## Verification

Run the registered focused test command, changed-scope coverage command, and `native-mtp-loader-safetensor-scandir` probe locally on Linux before opening the PR. PR-scoped performance CI remains the merge gate for the registered probe report.
