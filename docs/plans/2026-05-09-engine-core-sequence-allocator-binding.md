# Engine Core Sequence Allocator Binding

## Scope

This performance slice is limited to `EngineCore` event emission in
`services/mlx-worker-python/worker/engine/engine_core.py`.

The optimization preserves the existing event order and sequence numbers while
binding the active request state's `allocate_seq` method once per generate
request. This removes repeated attribute lookup work from the hot generate event
emission path without changing request lifecycle, usage accounting, stop
handling, or completed-event payloads.

## Registered Probe

The affected Python path is covered by the registered PR-scoped performance
probe `engine-generate-usage-token-elision` in
`infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `engine_core.py`, `test_generate_stream.py`,
`test_pr_scoped_performance.py`, and `scripts/engine_generate_usage_token_probe.py`.
This slice does not add a new registry entry because the registered probe already
watches the changed runtime path and exercises repeated no-usage `Generate`
event emission on Linux.

## Plan

1. Keep behavior covered by the registered focused generate tests.
2. Bind `state.allocate_seq` to a local callable after generate request state
   creation.
3. Use the local callable for generate event sequence allocation.
4. Run the registered focused tests, changed-scope coverage, and registered
   probe locally on Linux.
5. Use GitHub Actions and the registered PR-scoped performance workflow as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_generate_stream.py::test_generate_without_usage_skips_prompt_token_count_fallback services/mlx-worker-python/tests/test_generate_stream.py::test_sampling_with_resolved_stop_reuses_sampling_when_stop_sequences_match services/mlx-worker-python/tests/test_generate_stream.py::test_sampling_with_resolved_stop_clones_when_stop_sequences_change services/mlx-worker-python/tests/test_generate_stream.py::test_generate_usage_reuses_runtime_event_prompt_tokens_without_fallback_count services/mlx-worker-python/tests/test_generate_stream.py::test_generate_usage_counts_prompt_tokens_only_for_missing_event_total services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion_without_request_token_accumulation services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion_without_usage_preserves_finish_reason services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion services/mlx-worker-python/tests/test_generate_stream.py::test_generate_stream_exports_stop_contract_metrics_and_stops_at_turn_boundary services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_engine_generate_usage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_engine_generate_usage_token_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_generate_stream.py::test_generate_without_usage_skips_prompt_token_count_fallback services/mlx-worker-python/tests/test_generate_stream.py::test_sampling_with_resolved_stop_reuses_sampling_when_stop_sequences_match services/mlx-worker-python/tests/test_generate_stream.py::test_sampling_with_resolved_stop_clones_when_stop_sequences_change services/mlx-worker-python/tests/test_generate_stream.py::test_generate_usage_reuses_runtime_event_prompt_tokens_without_fallback_count services/mlx-worker-python/tests/test_generate_stream.py::test_generate_usage_counts_prompt_tokens_only_for_missing_event_total services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion_without_request_token_accumulation services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion_without_usage_preserves_finish_reason services/mlx-worker-python/tests/test_generate_stream.py::test_generate_streams_token_and_terminal_completion services/mlx-worker-python/tests/test_generate_stream.py::test_generate_stream_exports_stop_contract_metrics_and_stops_at_turn_boundary services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_engine_generate_usage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_engine_generate_usage_token_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/engine_core.py services/mlx-worker-python/tests/test_generate_stream.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/engine_generate_usage_token_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_ENGINE_GENERATE_USAGE_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/engine_generate_usage_token_probe.py
```
