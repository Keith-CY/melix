# Report evidence probe-phase rule cache

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._rule_matches_report()` rules that declare tuple-backed `probe_phases`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`
- `docs/plans/2026-06-27-report-evidence-probe-phase-cache.md`

The probe tracks aggregate evidence-gate matching plus run-kind, metric-prefix, target-field, matrix-role, dict-list, probe-phase, slowest-phase, release-matrix, and payload-loading timings. This slice extends the focused test and coverage commands to include the tuple probe-phase cache regression and the mutable list probe-phase regression.

## Optimization

Tuple-valued `probe_phases` rules are immutable and reused by release evidence matrices. Cache the normalized `frozenset[str]` directly on the rule object, matching the existing rule-local cache pattern for tuple `run_kinds`, `metric_prefixes`, and `target_fields`. Mutable non-tuple iterables still normalize per call so list mutation remains observable.

## Verification

Run locally on Linux using the registered focused commands from `report-evidence-gate-run-kind-set-membership`:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <registered focused test list>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <registered focused test list>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/report_evidence_gate.py services/mlx-worker-python/tests/test_report_evidence_gate.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/report_evidence_gate_run_kind_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_REPORT_EVIDENCE_GATE_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/report_evidence_gate_run_kind_probe.py
python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id report-evidence-gate-run-kind-set-membership --base-repo /root/.hermes/profiles/coder/workspace/melix --head-repo "$PWD" --output /tmp/report-evidence-probe-phase-cache.json
```

GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Local evidence

Linux local verification for branch `perf/report-evidence-probe-phase-cache-20260627`:

- Focused tests: `28 passed in 0.16s`.
- Changed-scope coverage: `TOTAL 12 0 100%`.
- Baseline direct probe before this slice:
  - `elapsed_ms_mean=1001.3340631965548`
  - `probe_phases_elapsed_ms_mean=53.03096040152013`
- Post-change direct probe:
  - `elapsed_ms_mean=976.5113841509447`
  - `probe_phases_elapsed_ms_mean=51.80103878956288`
- Direct single-worktree delta:
  - aggregate `elapsed_ms_mean` improved by `24.82267904561013 ms` (`2.4789608141731234%`, speedup `1.0254197538794623x`)
  - `probe_phases_elapsed_ms_mean` improved by `1.229921611957252 ms` (`2.3192520041971485%`, speedup `1.0237431843201774x`)
- Local PR-scoped runner (`python3 scripts/pr_scoped_performance_run.py --probe-id report-evidence-gate-run-kind-set-membership`) completed successfully and wrote `/tmp/report-evidence-probe-phase-cache.json`:
  - base `elapsed_ms_mean=967.7629733807407`, head `elapsed_ms_mean=960.3231998160481`, delta `-7.439773564692587 ms` (`0.7687598894905855%`, speedup `1.0077471559222122x`)
  - base `probe_phases_elapsed_ms_mean=52.61714200023562`, head `probe_phases_elapsed_ms_mean=51.113817014265805`, delta `-1.5033249859698117 ms` (`2.8571011818982486%`, speedup `1.0294113230782636x`)

CI still remains the merge gate for the registered probe report.

## Success criteria

- Focused tests pass.
- Changed-scope coverage for touched Python and probe files remains at or above 95%.
- Local and CI registered probe metrics show non-regression on aggregate `elapsed_ms_mean`, with expected improvement in phase-rule/matrix-role paths when tuple `probe_phases` rules are reused.
