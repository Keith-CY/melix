# Stream Assembler Delta Token Count Fast Path

This Python performance slice is limited to delta token-count estimation in
`services/mlx-worker-python/worker/runtime/stream_assembler.py`.

## Scope

`RequestStreamAssembler._annotate_token_counts(...)` estimates per-delta token
weights for multi-delta streaming fragments. The current implementation uses
`len(text.split())` for content and reasoning deltas, which materializes a list
for normalized ASCII text emitted by common token streams.

This slice adds a narrow long normalized-ASCII whitespace count helper and keeps
Python `split()` semantics for short deltas, leading/trailing spaces, repeated
spaces, ASCII control whitespace, and non-ASCII text.

## Registered probe

The affected path is covered by the existing registered PR-scoped probe:

- `stream-assembler-token-byte-fast-decode`

This slice extends that probe's metrics with a base-vs-head delta token-count
micro-workload:

- `delta_token_count_old_ms_mean`
- `delta_token_count_new_ms_mean`
- `delta_token_count_delta_ms`
- `delta_token_count_speedup`
- `delta_token_count_text_count`

## Verification plan

Run from the repository root on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_stream_assembler.py::test_estimated_delta_token_count_matches_split_semantics_without_ascii_allocation \
  services/mlx-worker-python/tests/test_stream_assembler.py::test_delta_token_annotation_uses_ascii_count_fast_path \
  services/mlx-worker-python/tests/test_stream_assembler.py::test_plain_token_metadata_keeps_fast_path_and_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_token_bytes_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_stream_assembler.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_token_bytes_probe_script_emits_metrics \
  && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json \
  && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
    services/mlx-worker-python/worker/runtime/stream_assembler.py \
    services/mlx-worker-python/tests/test_stream_assembler.py \
    services/mlx-worker-python/tests/test_pr_scoped_performance.py \
    scripts/stream_assembler_token_bytes_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py \
  --registry infra/perf/pr_scoped_probes.json \
  --probe-id stream-assembler-token-byte-fast-decode \
  --base-repo /root/.hermes/profiles/coder/workspace/melix \
  --head-repo "$PWD" \
  --output .runtime/stream-assembler-token-byte-fast-decode-report.json
```

PR-scoped performance CI remains the final registered probe validation source
before merge.
