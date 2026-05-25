# Hub Catalog Direct Card Size Label Fast Path

## Scope

This Python-only performance slice narrows Hub catalog size-hint parsing in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The affected path is covered by the registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` in
`infra/perf/pr_scoped_probes.json`, which declares focused `test_command`,
`coverage_command`, and `probe_command` entries.

## Behavior

Hub card metadata can expose `cardData.model_size` either as a bare size such as
`128 MB` or as a labeled value such as `Model size: 128 MB`. The previous direct
card helper attempted the bare-size parser before stripping the label, causing
labeled values to pay an avoidable split/error path before reaching the intended
labeled parser.

This slice checks and strips the `Model size` label first, then falls back to the
bare-size parser for unlabeled values. Parsing semantics stay unchanged for bare,
labeled, decimal, invalid, and empty values.

## Verification

Run the registered focused tests, changed-scope coverage command, and registered
size-hint probe locally on Linux. The PR-scoped performance workflow remains the
CI merge gate for the registered probe report.

Success criteria:

- focused Hub catalog tests pass;
- changed-scope coverage for the touched Hub catalog path remains at least 95%;
- the registered size-hint probe shows a neutral-to-improved elapsed mean versus
  the `origin/main` baseline.
