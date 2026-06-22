# Local job follow-up projection loop bindings

## Scope

This slice keeps the local job continuation scan behavior unchanged and narrows only the projection loop in `project_local_job_session_followups()`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for the local job continuation module, tests, registry selection, and `scripts/local_job_followup_scan_probe.py`.

## Optimization

The projection loop now binds the per-claim projection helper and list append methods once before iterating over scanned follow-up claims. This avoids repeated attribute/global lookups in large follow-up batches while preserving the existing copied receipt/refusal output contract.

## Verification plan

1. Run the focused local job continuation tests from the registered probe.
2. Run changed-scope coverage from the registered probe and remove generated `coverage.json` afterwards.
3. Run `scripts/local_job_followup_scan_probe.py` locally on Linux and compare the local projection/scan metrics with the pre-change baseline.
4. Use the PR-scoped performance workflow as the merge gate before squash merging.
