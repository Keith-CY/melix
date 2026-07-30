# Report Evidence Load JSON Binding Performance Slice

This Python-only slice is limited to the report-evidence gate JSON loading path
in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The affected path is covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries and reports
`load_report_payload_elapsed_ms_mean` alongside the broader report-evidence gate
timings.

## Slice

`load_report_payload(...)` now reuses a module-local `json.loads` binding while
continuing to read report JSON as bytes and preserve the same decode and payload
validation behavior. This avoids repeated module attribute resolution in the
registered probe's repeated report-load loop without changing accepted payloads
or error handling.

## Verification

1. Run the registered focused test command for
   `report-evidence-gate-run-kind-set-membership`.
2. Run changed-scope coverage using the registered coverage command.
3. Run the registered probe locally on Linux and compare the report-load timing
   against the pre-change baseline.
