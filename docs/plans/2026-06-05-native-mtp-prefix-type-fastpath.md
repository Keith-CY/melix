# Native MTP Prefix Type Fast Path

## Scope

This Python-only performance slice is limited to `worker.runtime.native_mtp.mlx_lm_loader._is_mtp_weight_key`.
Native-MTP index maps are dominated by exact `str` keys, so the prefix classifier should take a direct exact-string path while preserving support for `str` subclasses and custom key objects that rely on `str(key)`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `native-mtp-loader-safetensor-scandir` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and runs `scripts/native_mtp_loader_safetensor_scandir_probe.py`.

## Plan

1. Preserve native-MTP index parsing semantics for exact strings, `str` subclasses, and custom key objects.
2. Add a focused regression assertion covering the `str` subclass fallback branch.
3. Implement the exact-string fast path before the existing `isinstance` and `str(key)` fallback checks.
4. Verify with the registered focused tests, changed-scope coverage, and the registered local Linux probe; use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by the registered probe's `key_new_mean_ms` / `key_old_mean_ms` and overall native-MTP loader metrics from `scripts/native_mtp_loader_safetensor_scandir_probe.py`; behavior parity is measured by focused native-MTP loader tests and changed-scope coverage for the touched module.
