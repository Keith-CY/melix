# Engine Core Shared Whitespace Token Count Cache

## Scope

This performance slice is limited to fallback prompt-token counting in
`services/mlx-worker-python/worker/engine/engine_core.py`.

When a runtime token event does not provide `prompt_tokens` and the runtime does
not expose `prompt_token_count(...)`, `EngineCore.generate(...)` falls back to a
zero-allocation whitespace token scan. The same repository already provides the
cached implementation in `worker.runtime.token_counting.whitespace_token_count`,
which is used by other runtime paths. This slice reuses that shared cached helper
from `EngineCore` so repeated identical prompts avoid rescanning the full prompt
while preserving `str.split(None)`-style token boundaries and avoiding split-list
allocation.

## Registered Probe

The affected Python path is covered by the registered PR-scoped performance
probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` values for `engine_core.py`, `test_generate_stream.py`,
`test_pr_scoped_performance.py`, and `scripts/engine_generate_usage_token_probe.py`.

This slice does not add a new registry entry because the existing registered
probe already measures the fallback token-count path with
`fallback_elapsed_ms_mean` and `fallback_peak_bytes_mean`.

## Plan

1. Add focused regression coverage that `_whitespace_token_count(...)` still
   matches `str.split(None)` token semantics for mixed whitespace and that the
   shared cache is reused on repeated prompts.
2. Replace the private `EngineCore` fallback scanner with the shared cached
   `worker.runtime.token_counting.whitespace_token_count` helper.
3. Run the registered focused tests, changed-scope coverage, and registered
   probe locally on Linux.
4. Use GitHub Actions and the registered PR-scoped performance workflow as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_generate_stream.py::test_generate_without_usage_skips_prompt_token_count_fallback services/mlx-worker-python/tests/test_generate_stream.py::test_sampling_with_resolved_stop_reuses_sampling_when_stop_sequences_match services/mlx-worker-python/tests/test_generate_stream.py::test_sampling_with_resolved_stop_clones_when_stop_sequences_change services/mlx-worker-python/tests/test_generate_stream.py::test_generate_usage_reuses_runtime_event_prompt_tokens_without_fallback_count services/mlx-worker-python/tests/test_generate_stream.py::test_generate_usage_counts_prompt_tokens_only_for_missing_event_total services/mlx-worker-python/tests/test_generate_stream.py::test_whitespace_token_count_matches_split_semantics_and_reuses_shared_cache services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion_without_request_token_accumulation services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion_without_usage_preserves_finish_reason services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion services/mlx-worker-python/tests/test_generate_stream.py::test_generate_stream_exports_stop_contract_metrics_and_stops_at_turn_boundary services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_engine_generate_usage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_engine_generate_usage_token_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_generate_stream.py::test_generate_without_usage_skips_prompt_token_count_fallback services/mlx-worker-python/tests/test_generate_stream.py::test_sampling_with_resolved_stop_reuses_sampling_when_stop_sequences_match services/mlx-worker-python/tests/test_generate_stream.py::test_sampling_with_resolved_stop_clones_when_stop_sequences_change services/mlx-worker-python/tests/test_generate_stream.py::test_generate_usage_reuses_runtime_event_prompt_tokens_without_fallback_count services/mlx-worker-python/tests/test_generate_stream.py::test_generate_usage_counts_prompt_tokens_only_for_missing_event_total services/mlx-worker-python/tests/test_generate_stream.py::test_whitespace_token_count_matches_split_semantics_and_reuses_shared_cache services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion_without_request_token_accumulation services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion_without_usage_preserves_finish_reason services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion services/mlx-worker-python/tests/test_generate_stream.py::test_generate_stream_exports_stop_contract_metrics_and_stops_at_turn_boundary services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_engine_generate_usage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_engine_generate_usage_token_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/engine_core.py services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/engine_generate_usage_token_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_ENGINE_GENERATE_USAGE_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/engine_generate_usage_token_probe.py
```

Local Linux probe result for the fallback token-count path:

- Baseline (`origin/main`): `fallback_elapsed_ms_mean=246.89380615018308`,
  `fallback_peak_bytes_mean=73977.8`.
- Slice: `fallback_elapsed_ms_mean=110.89347582310438`,
  `fallback_peak_bytes_mean=81003.6`.
- Delta: `-136.0003303270787 ms` (`2.226405x`, `55.08%` lower mean elapsed),
  with a modest peak-memory increase from cache reuse.
