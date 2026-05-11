# Vision Family Token Media Aggregation Slice

## Scope

This Python-only performance slice keeps `ResolvedVisionFamilyConfig.prompt_token_count()` behavior unchanged while reducing per-frame arithmetic in media-token accounting.

## Registered Probe

The affected path is covered by the PR-scoped `vision-family-prompt-token-count-scan` probe in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `scripts/vision_family_prompt_token_count_probe.py`

## Optimization Hypothesis

The current prompt token path already caches prompt whitespace scans. Remaining hot work in this probe is media token aggregation across images and video frame policies. Keeping image minimum clamping inline and aggregating video frame counts once should reduce loop work while preserving the existing minimum-one-token semantics for empty or non-positive frame policies.

## Verification Plan

- Run the focused registered pytest command for `vision-family-prompt-token-count-scan`.
- Run the registered changed-scope coverage command and require at least 95% for the touched scope.
- Run the registered probe locally on Linux against `origin/main` and the head worktree.
- Use GitHub Actions and the PR-scoped performance workflow as the merge gate.

## Linux Boundary

This slice changes Python worker code only and is locally verifiable on Linux. No Swift runtime performance claim is made.
