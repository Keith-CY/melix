# Report evidence target-field text fast path

## Slice

Optimize exactly one Python hot path in report evidence matrix matching:
`_has_text()` in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The affected path is covered by the registered PR-scoped performance probe
`report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.
The registry entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `report_evidence_gate.py`, its focused tests, and
`scripts/report_evidence_gate_run_kind_probe.py`.

## Hypothesis

Target-field matrix rules frequently evaluate exact `str` values that are already
non-empty. `_has_text()` previously called `str.strip()` for every exact string
value, allocating a trimmed string for padded values and performing more work
than needed to distinguish blank from present text. A type-exact string fast path
can use `str.isspace()` to preserve blank and padded-string semantics while
avoiding `strip()` on common exact strings and keeping subclass/non-string
behavior unchanged.

## Scope

- Keep target-field rule behavior identical for empty strings, whitespace-only
  strings, padded strings, string subclasses, and non-string values.
- Do not change release matrix rule ordering, report rendering, probe selection,
  or probe registry semantics.
- Use the existing registered probe as the local and CI performance gate.

## Verification

Run the registered probe's focused tests, changed-scope coverage command, and
probe command locally on Linux. CI PR-scoped performance must complete
successfully before merge.