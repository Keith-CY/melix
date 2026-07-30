# Hub catalog card model-size prefix direct path

This Python-only performance slice is limited to Hub catalog card `model_size`
parsing in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches the Hub catalog implementation, focused
Hub catalog tests, PR-scoped performance tests, and the size-hint probe script.

## Slice

The direct card-size parser now handles the common exact prefixes
`MODEL SIZE:`, `MODEL SIZE|`, and `Model size: ` before falling back to the more
general label stripper. This preserves the same accepted labels and regex
fallback behavior while avoiding the helper dispatch for the most common
cardData `model_size` strings.

## Verification plan

- Run focused Hub catalog tests and the registered probe-emission test.
- Run changed-scope coverage for the registered probe scope.
- Run `scripts/hub_catalog_size_hint_probe.py` locally on Linux and compare
  against the pre-change baseline.
- Use the PR-scoped performance workflow as the merge gate for registered CI
  probe validation.

## Expected metrics

The local probe should preserve `size_hint_calls_mean=0.0` and reduce
`elapsed_ms_mean` for the size-hint parser path. Compatibility metrics are
unchanged and remain in the same registered probe for regression visibility.
