# Native MTP duplicate sidecar filter slice

## Scope

This Python-only performance slice is limited to
`services/mlx-worker-python/worker/runtime/native_mtp/mlx_lm_loader.py`.
`extra_mtp_safetensor_files()` already filters ordinary model shards before
joining sidecar paths. This slice keeps the same sidecar discovery semantics but
records the raw file-name dedupe set before computing the basename for repeated
MTP sidecar entries, including duplicate model-shard and non-safetensor names.

## Registered probe

Registered PR-scoped probe: `native-mtp-loader-safetensor-scandir` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries for this loader, its unit coverage, and
`scripts/native_mtp_loader_safetensor_scandir_probe.py`. The probe includes a
duplicate-MTP-entry workload and gates `extra_new_mean_ms`, `extra_delta_ms`,
`extra_speedup`, and allocation metrics for `extra_mtp_safetensor_files()`.
The JSON read `delta_ms` and `speedup` ratios are reported as informational
control metrics because they are derived from an unchanged helper and have shown
CI jitter even when absolute `new_mean_ms` remains inside threshold.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux. The GitHub PR-scoped performance workflow is
the merge gate for CI validation.

## Acceptance criteria

- Duplicate sidecar, model-shard, and non-safetensor file names are skipped
  before basename/path filtering.
- The native-MTP focused tests and changed-scope coverage remain green.
- The registered probe shows directionally lower `extra_new_mean_ms` or an
  acceptable non-regression for the duplicate-sidecar workload.
