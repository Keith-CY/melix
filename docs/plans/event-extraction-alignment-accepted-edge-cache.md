# Event Extraction Alignment Accepted-Edge Cache

## Goal

Reduce redundant work in `worker.productization.event_extraction._maximum_weight_event_matching` by precomputing accepted prediction edges for each gold event before the dynamic-programming search.

## Linux-only constraint

This slice is Python-only and can be verified on Linux with focused pytest, changed-scope coverage, and an explicit local performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `scripts/event_extraction_alignment_probe.py`

## Probe definition

Register `event-extraction-alignment-accepted-edge-cache` in the PR-scoped performance registry. The probe builds a deterministic sparse alignment matrix and repeatedly calls `_maximum_weight_event_matching`, reporting:

- `elapsed_ms_mean` — lower is better
- `accepted_edges` — informational structural metric
- `matrix_size`, `iterations_per_sample`, `sample_count`, `match_count_mean`, and `checksum` for workload integrity

## Success metrics

- Focused tests pass.
- Changed-scope automated coverage is at least 95%.
- The local probe produces concrete metrics and the base-vs-head comparison improves `elapsed_ms_mean` without changing the matching checksum.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_event_extraction.py::test_event_alignment_uses_global_optimum_not_greedy \
  services/mlx-worker-python/tests/test_event_extraction.py::test_event_alignment_precomputes_only_accepted_sparse_edges \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_event_extraction_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_event_extraction_alignment_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <same test selection>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/event_extraction.py \
  services/mlx-worker-python/tests/test_event_extraction.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/event_extraction_alignment_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/event_extraction_alignment_probe.py
```
