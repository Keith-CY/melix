# Report evidence load Path fast path

This Python-only performance slice keeps report evidence semantics unchanged while avoiding redundant `Path(...)` construction in the report JSON loader when callers already pass a `Path` object.

## Affected path

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`
- `infra/perf/pr_scoped_probes.json`

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries, and its metrics include `load_report_payload_elapsed_ms_mean` for the JSON payload loader.

## Optimization

`load_report_payload()` previously wrapped every input in `Path(path)`. The probe and most internal callers already pass concrete `Path` instances, so this slice keeps those objects directly and only constructs a new `Path` for string/path-like inputs.

The change preserves:

- byte-oriented JSON reads via `Path.read_bytes()`;
- invalid JSON and non-object validation errors;
- support for string report paths.

## Verification

Run the registered focused tests, changed-scope coverage, and the registered PR-scoped performance probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

Expected local commands:

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py::test_load_report_payload_reads_json_bytes services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_covers_invalid_payload_and_edge_summaries services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_report_evidence_gate.py::test_load_report_payload_reads_json_bytes services/mlx-worker-python/tests/test_report_evidence_gate.py::test_report_evidence_gate_covers_invalid_payload_and_edge_summaries services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_report_evidence_gate_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_evidence_gate_run_kind_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/report_evidence_gate.py services/mlx-worker-python/tests/test_report_evidence_gate.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/report_evidence_gate_run_kind_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id report-evidence-gate-run-kind-set-membership --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/report_evidence_load_path_probe.json
```

## Success metrics

- Focused tests pass.
- Changed-scope coverage remains at least 95%.
- The registered probe reports a lower `load_report_payload_elapsed_ms_mean` without in-scope regressions.
