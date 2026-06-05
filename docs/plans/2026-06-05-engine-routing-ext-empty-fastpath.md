# Engine Routing Ext Empty Fast Path Slice

## Scope

This Python-only performance slice is limited to `worker.engine.engine_core.EngineCore.generate()` routing metadata construction before the runtime `generate_tokens()` call.

## Registered probe

The affected path is covered by the registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries and watches `services/mlx-worker-python/worker/engine/engine_core.py`, focused Generate tests, the PR-scoped performance tests, and `scripts/engine_generate_usage_token_probe.py`.

This slice extends that focused test/coverage command with routing-ext behavior tests so the empty execution-ext and client-ext preservation paths are covered by the same registered probe.

## Implementation plan

1. Preserve runtime routing metadata semantics for empty `execution.ext`, non-empty client `execution.ext`, positive preferred block size, acceleration mode, cache mode, session id, model id, and revision.
2. Replace the empty-`execution.ext` incremental dict construction with a literal fast path while keeping the non-empty path as a copy of client-provided metadata plus Melix routing keys.
3. Add focused regression tests proving the request proto map is not mutated and that runtime `execution_ext` receives identical routing metadata.
4. Run focused Generate tests, changed-scope coverage, and the registered local probe on Linux.
5. Use the PR-scoped performance workflow as the merge gate for the registered probe report.

## Success criteria

- Focused Generate tests pass.
- Changed-scope coverage for the touched files remains above the repository threshold.
- The registered probe reports stable/improved no-usage Generate latency without regressing fallback usage metrics.
