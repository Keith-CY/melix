# Native MTP weight-key str fast path

## Scope

This Python-only performance slice is limited to `worker.runtime.native_mtp.mlx_lm_loader._is_mtp_weight_key()` in the native-MTP sidecar safetensor discovery path. The registered probe exercises thousands of normal `str` weight-map keys, so the hot path now calls `startswith()` directly on string-like keys and only falls back to `str(key)` for non-string/custom mapping keys that do not expose a compatible prefix check.

## Probe

Registered PR-scoped probe: `native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.

The affected path is already covered by focused `test_command`, `coverage_command`, and `probe_command` entries. The probe reports dedicated key-prefix predicate metrics (`key_old_mean_ms`, `key_new_mean_ms`, `key_delta_ms`, `key_speedup`) alongside the native-MTP JSON and sidecar scan metrics. Baseline-only `old_*` metrics are informational so scheduler noise in unchanged local baseline helpers does not block this slice; candidate and delta/speedup metrics remain gated.

## Verification

Run the registered focused test command, changed-scope coverage command, and the registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
