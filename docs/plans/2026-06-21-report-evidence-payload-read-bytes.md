# Report evidence payload read-bytes performance slice

## Scope

This Python-only performance slice is limited to loading report-evidence gate JSON payloads in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The registered PR-scoped performance probe is `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The slice extends that probe with `load_report_payload_elapsed_ms_mean` so CI and local runs measure the changed JSON payload-loading path directly.

## Optimization

`load_report_payload` should read the JSON file as bytes and pass those bytes directly to `json.loads`. This avoids the separate `Path.read_text(..., encoding="utf-8")` decode step while preserving JSON object validation and decode-error handling for malformed JSON.

## Follow-up: run-kind tuple rule cache

The next Python-only slice keeps the same registered PR-scoped performance probe (`report-evidence-gate-run-kind-set-membership`) and narrows the implementation change to `_rule_matches_report` run-kind matching. Tuple run-kind rules are stable in the release-evidence matrix hot path, so the normalized run-kind `frozenset` is cached on the rule dict after the first match call. List/set rules still rebuild from the live iterable so mutation-sensitive behavior is preserved.

Additional verification for this slice:

- Add a regression test that proves tuple rules keep and reuse the normalized rule-local set.
- Re-run the focused report evidence gate tests, changed-scope coverage, and the registered probe locally on Linux.

## Success Criteria

- Focused tests pass locally on Linux.
- Changed-scope coverage for touched files is at least 95%.
- The registered probe shows a lower `run_kind_elapsed_ms_mean` for the candidate implementation versus the baseline, or CI reports the registered probe as successful with no in-scope regression.
