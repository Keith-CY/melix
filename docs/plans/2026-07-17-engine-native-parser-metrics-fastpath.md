# Engine Native Parser Metrics Plain-Token Fast Path

## Scope

This Python-only performance slice is limited to terminal Generate response
metrics assembly in `worker.engine.engine_core.EngineCore.generate()`.

Plain text token events do not carry native-MTP timing, speculative decoding, or
prefix-cache parser metrics. The hot Generate finalization path should avoid
calling the native parser-metrics materializer for those events while preserving
all existing metrics when native parser metadata is present.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`.
The probe has focused `test_command`, `coverage_command`, and `probe_command`
entries and watches:

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/engine_generate_usage_token_probe.py`

## Implementation plan

1. Preserve Generate response semantics and all native parser metrics when the
   runtime token event includes native-MTP timing, speculative, or prefix-cache
   fields.
2. Add a lightweight predicate for whether a runtime token event can emit native
   parser metrics.
3. Use that predicate before materializing native parser metrics during Generate
   finalization so plain token events skip the empty metrics helper path.
4. Add focused regression coverage proving plain usage-tracked token events do
   not call the native parser metrics materializer.
5. Run the registered focused tests, changed-scope coverage, and registered
   probe locally on Linux before pushing. GitHub Actions PR-scoped performance
   remains the merge gate.

## Success criteria

- Focused Generate tests pass.
- Changed-scope coverage for the touched files remains above the repository
  threshold.
- The registered local probe remains green and reports stable/improved metrics
  for Generate no-usage and fallback usage paths.
