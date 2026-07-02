# Report Evidence Probe Phase Direct Bucket Scan

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._probe_phases`.

## Scope

- Preserve probe-phase extraction from `baseline` and `candidate` `probe_summary` buckets.
- Preserve malformed-bucket tolerance, dict-only row handling, phase stringification, and whitespace trimming.
- Avoid calling `_dict_list(...)` for each bucket because `_probe_phases` only needs to stream valid dict rows into a set and does not need the helper's list identity/materialization behavior.
- Keep the implementation local to report evidence gate code, its focused regression coverage, this plan, and the registered PR-scoped probe metadata.

## Registered probe

The affected path is covered by the existing `report-evidence-gate-run-kind-set-membership` entry in `infra/perf/pr_scoped_probes.json`.

That registered probe provides focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/report_evidence_gate.py`. This slice extends the probe with `probe_phases_elapsed_ms_mean` so CI and local runs measure `_probe_phases(...)` directly.

## Verification plan

1. Run the registered focused test command locally on Linux, including the new regression test that guards direct bucket scanning.
2. Run the registered changed-scope coverage command locally on Linux and confirm the touched scope remains at or above 95%.
3. Run the registered probe locally on Linux against `origin/main` and this branch, comparing `probe_phases_elapsed_ms_mean` and overall `elapsed_ms_mean`.
4. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Expected performance signal

The expected signal is a small reduction in `probe_phases_elapsed_ms_mean` from replacing repeated `_dict_list(...)` helper calls with direct list checks inside `_probe_phases(...)`. Overall `elapsed_ms_mean` may move only slightly because this is one subpath of the broader report-evidence gate probe.
