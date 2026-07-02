# Vision family media request token-count cache

## Scope

This Python-only performance slice is limited to `ResolvedVisionFamilyConfig.prompt_token_count()` in `worker.runtime.vision_family_adapters`. It keeps the existing whitespace token-counting helper and media-token semantics unchanged while avoiding repeated image/video token scans when the same prepared media request is counted repeatedly by the same resolved family config.

## Registered probe

The affected path is covered by the registered PR-scoped probe `vision-family-prompt-token-count-scan` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`
- `services/mlx-worker-python/worker/runtime/token_counting.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/vision_family_prompt_token_count_probe.py`

This slice extends the focused test command with the new same-media-request cache regression test.

## Plan

1. Preserve text-only prompt count behavior and its existing `_whitespace_token_count` cache expectations.
2. Add a single-entry identity cache on resolved vision family configs for media-bearing `PreparedVisionRequest` objects.
3. Cache only media-bearing requests so text-only cache accounting and fallback behavior remain unchanged.
4. Add regression coverage proving a same-object media request cache hit does not rescan prompt or media lists.
5. Run the focused registry tests, changed-scope coverage, and the registered local Linux probe before opening the PR.

## Acceptance

- Focused vision-family prompt-token tests pass locally.
- Changed-scope coverage for the touched Python/test/probe registry scope is at least 95%.
- The registered local probe reports a directionally lower elapsed time for repeated media request token counts.
- GitHub Actions, including the PR-scoped performance workflow, complete successfully before merge.
