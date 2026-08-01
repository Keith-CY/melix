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

## 2026-08-01 Allowed-Tools Empty Source-ID Slice

This follow-up Python-only slice stays within `EngineCore._allowed_tools_receipt_json()`.
When `melix.mcp.source_ids` is absent or whitespace-only but other tool receipt
metadata forces receipt materialization, normalize the source-id text once and
skip the comma split entirely for the empty case. Behavior remains unchanged:
declared source IDs are still trimmed, empty segments are ignored, and omitted
source IDs still emit an empty `tool_source_ids` array.

The affected file is already covered by the registered PR-scoped performance
probe `engine-generate-usage-token-elision`, including focused `test_command`,
`coverage_command`, and `probe_command` entries. Local Linux verification uses
the registered focused tests, changed-scope coverage, the registered probe, and
a direct microprobe for the empty-source-id receipt path.
