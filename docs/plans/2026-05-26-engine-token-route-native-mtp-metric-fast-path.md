# Engine native-MTP parser metric empty fast path

## Scope

This Python-only performance slice is limited to `EngineCore` completion metrics assembly in `services/mlx-worker-python/worker/engine/engine_core.py`.

The current completion path always builds a native-MTP/speculative parser-metric candidate dictionary when a final `RuntimeTokenEvent` exists, even when the event carries no native-MTP timings and no speculative token counters. The common deterministic/local test runtimes and non-MTP text generation paths fall into that empty-metric case.

## Registered probe

The affected path is covered by the registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`.

The probe already defines focused `test_command`, `coverage_command`, and `probe_command` entries for `engine_core.py`, generate-stream tests, probe-selection tests, and `scripts/engine_generate_usage_token_probe.py`. This slice extends the registered test and coverage commands with the native-MTP parser metric regression tests and uses the probe as the local Linux and CI performance gate.

## Implementation plan

1. Add a regression test proving empty native-MTP/speculative runtime events return no parser metrics.
2. Add a single early return in `_text_native_mtp_parser_metrics(...)` for the empty-event case.
3. Run the registered focused tests, changed-scope coverage, and registered probe locally on Linux.
4. Use GitHub Actions PR-scoped performance as the final merge gate.

## Metrics

Primary registered probe metrics:

- `elapsed_ms_mean`: lower is better for no-usage generate requests.
- `fallback_elapsed_ms_mean`: lower is better for return-usage fallback requests.
- `prompt_token_count_calls_per_request`: unchanged at `0` for no-usage requests.
- `request_state_append_calls_per_request`: unchanged.

Success means behavior tests pass, changed-scope coverage remains at least 95%, and the registered probe does not regress on CI.
