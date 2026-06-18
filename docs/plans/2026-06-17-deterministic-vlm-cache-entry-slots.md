# Deterministic VLM Cache Entry Slots

## Scope

This Python performance slice is limited to `VisionCacheEntry` in
`services/mlx-worker-python/worker/runtime/deterministic_vlm_runtime.py`.

The optimization preserves deterministic VLM cache identity fields and cache-hit
behavior while making the frozen cache-entry record slotted. This removes the
per-entry instance dictionary for the hot deterministic VLM cache-entry creation
path.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`deterministic-vlm-completion-token-scan` in `infra/perf/pr_scoped_probes.json`.
The registered probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `deterministic_vlm_runtime.py`,
`test_vision_runtime.py`, `test_pr_scoped_performance.py`, and
`scripts/deterministic_vlm_completion_token_probe.py`.

No registry change is needed for this slice because the probe watches the changed
runtime file and repeatedly creates deterministic VLM cache entries while
measuring elapsed time and peak bytes.

## Plan

1. Keep the slice limited to the cache-entry record shape.
2. Add `slots=True` to `VisionCacheEntry` without changing fields or behavior.
3. Run focused tests, changed-scope coverage, and the registered probe locally on
   Linux; compare against the pre-change baseline.
4. Use GitHub Actions and the registered PR-scoped performance workflow as the
   merge gate.

## Expected Performance Signal

The primary signal is lower `peak_bytes_mean` in the registered deterministic VLM
completion-token probe. `elapsed_ms_mean` may also improve from reduced instance
allocation overhead, but memory reduction is the key metric for this slice.
