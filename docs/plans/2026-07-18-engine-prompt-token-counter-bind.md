# Engine generate prompt token counter binding

## Slice

Optimize the generate usage trailer path in `services/mlx-worker-python/worker/engine/engine_core.py` by resolving the optional runtime `prompt_token_count` callable once per request instead of probing the runtime attribute at usage-finalization time.

## Registered probe

The affected path is covered by registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/engine_generate_usage_token_probe.py`

## Optimization hypothesis

Usage accounting only needs to know whether the runtime provides `prompt_token_count`. Binding that optional callable once keeps behavior equivalent while removing repeated attribute-existence checks from the usage fallback path. Requests with `return_usage=false` keep the value as `None` and continue to avoid prompt-token accounting work.

## Validation plan

1. Run the focused tests from the registered probe locally on Linux.
2. Run the changed-scope coverage command from the registered probe locally on Linux.
3. Run the registered probe locally on Linux before and after the change and compare `fallback_elapsed_ms_mean`, `elapsed_ms_mean`, and counter metrics.
4. Use GitHub Actions PR-scoped performance as the final registered probe validation and merge gate.

## Acceptance

Accept only if behavior tests pass, changed-scope coverage remains at or above 95%, and the registered probe does not regress usage-elision counters while improving or holding elapsed metrics within noise.
