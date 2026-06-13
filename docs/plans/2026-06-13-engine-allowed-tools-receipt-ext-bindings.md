# Engine allowed-tools receipt ext binding slice

This Python performance slice is limited to `EngineCore._allowed_tools_receipt_json()` in `services/mlx-worker-python/worker/engine/engine_core.py`.

## Scope

The slice keeps generate parser receipt behavior unchanged while reducing repeated protobuf-map lookups and duplicate source-id trimming work when the allowed-tools receipt must be assembled.

## Registered probe

The affected path is covered by the registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. The registry includes focused `test_command`, `coverage_command`, and `probe_command` entries and now includes the direct regression test for trimmed MCP source IDs.

## Verification plan

1. Run the registered focused test command for `engine-generate-usage-token-elision`.
2. Run the registered changed-scope coverage command and require at least 95% changed-line coverage.
3. Run the registered `engine_generate_usage_token_probe.py` command locally on Linux and compare against the pre-change probe output.
4. Let GitHub Actions run the PR-scoped performance workflow before merge.
