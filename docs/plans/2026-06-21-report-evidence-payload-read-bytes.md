# Report evidence payload read-bytes performance slice

## Scope

This Python-only performance slice is limited to loading report-evidence gate JSON payloads in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The registered PR-scoped performance probe is `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The slice extends that probe with `load_report_payload_elapsed_ms_mean` so CI and local runs measure the changed JSON payload-loading path directly.

## Optimization

`load_report_payload` should read the JSON file as bytes and pass those bytes directly to `json.loads`. This avoids the separate `Path.read_text(..., encoding="utf-8")` decode step while preserving JSON object validation and decode-error handling for malformed JSON.

## Verification

- Focused report evidence gate tests must include a regression that fails if `load_report_payload` uses `Path.read_text`.
- Changed-scope coverage must include the report evidence gate module, its tests, the PR-scoped performance test, and the probe script.
- The registered probe must emit `load_report_payload_elapsed_ms_mean` alongside the existing report-evidence gate timings.

## Success Criteria

- Focused tests pass locally on Linux.
- Changed-scope coverage for touched files is at least 95%.
- The registered probe shows a lower `load_report_payload_elapsed_ms_mean` for the candidate implementation versus the baseline, or CI reports the registered probe as successful with no in-scope regression.
