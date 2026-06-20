# Report Evidence Gate Run-Kind Disjoint Fast Path

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._run_kind_rule_matches`.

## Scope

- Preserve release matrix run-kind matching semantics for tuple rules, including exact string matches and stringified non-string fallback values.
- Use `frozenset.isdisjoint()` as the primary tuple-backed rule fast path so common all-string run-kind matching runs in C before falling back to Python-level stringification for non-string rule entries.
- Keep the slice local to report evidence gate code, focused registered tests, and this governing plan.

## Registered probe

The affected path is covered by the existing `report-evidence-gate-run-kind-set-membership` registered PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`.

The registered probe provides focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/report_evidence_gate.py`, and reports `run_kind_elapsed_ms_mean` from `scripts/report_evidence_gate_run_kind_probe.py`.

## Verification plan

1. Run the focused registered test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and confirm touched scope remains at or above 95%.
3. Run the registered probe command locally on Linux and compare `run_kind_elapsed_ms_mean` against the synced `origin/main` baseline.
4. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Expected performance signal

The primary expected signal is lower `run_kind_elapsed_ms_mean` from the registered probe. Overall `elapsed_ms_mean` may improve slightly; non-run-kind submetrics are not targeted by this slice.
