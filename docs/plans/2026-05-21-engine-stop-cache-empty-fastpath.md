# Engine Stop-Contract Empty-Stop Cache Fast Path

## Scope

Optimize one Python hot path in `EngineCore.generate`: resolving the stop-contract cache key for the common case where the request sampling config has no explicit stop sequences.

## Probe

The affected path is covered by the registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes:

- focused behavior tests through `test_command`
- changed-scope coverage through `coverage_command`
- repeated local/CI metrics through `scripts/engine_generate_usage_token_probe.py`

Primary metric for this slice: `elapsed_ms_mean` from the no-usage generate loop. Guard metrics remain `prompt_token_count_calls_per_request` and `request_state_append_calls_per_request`.

## Plan

1. Preserve stop-contract cache behavior for empty and explicit stop-sequence requests.
2. Avoid constructing a generator-backed tuple for the no-stop cache-key path by using the canonical empty tuple directly.
3. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before PR creation.
4. Use GitHub Actions PR-scoped performance output as the merge gate.

## Verification Notes

Local Linux verification is sufficient for this Python slice. No Swift runtime effect is claimed.
