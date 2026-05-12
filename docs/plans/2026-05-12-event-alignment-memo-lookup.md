# Event Alignment Memo Lookup Optimization

## Goal

Reduce hot-path overhead in `services/mlx-worker-python/worker/productization/event_extraction.py` event-alignment matching by avoiding a double dictionary lookup on recursive memo hits.

## Scope

- Change exactly one Python optimization point in `_maximum_weight_event_matching`.
- Keep event alignment semantics, tie-breaking, and audit payloads unchanged.
- Use the existing registered PR-scoped probe `event-extraction-alignment-accepted-edge-cache` for tests, coverage, and performance validation.

## Verification

Focused local Linux verification for this slice:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_event_extraction.py::test_event_alignment_uses_global_optimum_not_greedy \
  services/mlx-worker-python/tests/test_event_extraction.py::test_event_alignment_precomputes_only_accepted_sparse_edges \
  services/mlx-worker-python/tests/test_event_extraction.py::test_string_similarity_reuses_normalized_text_and_bigram_counts \
  services/mlx-worker-python/tests/test_event_extraction.py::test_evaluate_event_extraction_reuses_alignment_payloads_for_matched_details \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_event_extraction_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_event_extraction_alignment_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same focused tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/event_extraction.py \
  services/mlx-worker-python/tests/test_event_extraction.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/event_extraction_alignment_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/event_extraction_alignment_probe.py
```

## Metrics

Baseline from `origin/main` before the change:

- `elapsed_ms_mean=2235.686690825969`
- `elapsed_ms_min=2177.56721295882`
- `accepted_edges=28.0`
- `matrix_size=14.0`

Candidate after the memo-hit lookup change:

- `elapsed_ms_mean=2101.789930392988`
- `elapsed_ms_min=2021.0835839388892`
- `accepted_edges=28.0`
- `matrix_size=14.0`

The local registered probe shows a mean reduction of about 133.897 ms (about 6.0%) for the targeted alignment workload.
