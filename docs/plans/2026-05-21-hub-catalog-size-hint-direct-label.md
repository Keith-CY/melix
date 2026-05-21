# Hub Catalog Direct Model-Size Label Performance Slice

## Scope

Optimize only the Hub catalog `cardData.model_size` parsing path in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Registered Probe

The governing PR-scoped registered probe is
`hub-catalog-size-hint-regex-precompile` in
`infra/perf/pr_scoped_probes.json`. It already defines focused
`test_command`, `coverage_command`, and `probe_command` entries for the Hub
catalog size-hint path.

## Slice Plan

1. Keep the existing regex-backed fallback semantics for non-direct text fields.
2. Add a direct parser for common `cardData.model_size` values that include the
   literal `Model size` label before the numeric size.
3. Update the registered probe payload to include the labeled direct-card form so
   CI and local reports measure the regex-call elision.
4. Verify focused Hub catalog tests, changed-scope coverage, and the registered
   probe locally on Linux before opening the PR.

## Success Metrics

- `size_hint_calls_mean` should drop for the updated registered probe because
  labeled direct-card values no longer need `_size_hint_from_text`.
- `elapsed_ms_mean` is lower-is-better and should not regress materially.
- Behavior remains equivalent for direct-card labeled model-size values and for
  fallback parsing of non-direct text fields.
