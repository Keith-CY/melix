# Text Family Metadata Copy Elision

## Context

`resolve_text_family_config()` is used while resolving text model adapter metadata. The existing registered probe `text-family-config-copy-elision` already covers the config payload mapping path and focused tests for `services/mlx-worker-python/worker/runtime/text_family_adapters.py`.

## Slice

This slice keeps the existing behavior but avoids eagerly copying the metadata mapping passed to `resolve_text_family_config()`. The function only reads metadata values, so a read-only mapping is sufficient and preserves support for custom mapping implementations.

## Probe

The existing registered PR-scoped probe remains the governing performance signal:

- `infra/perf/pr_scoped_probes.json` id: `text-family-config-copy-elision`
- focused tests: `services/mlx-worker-python/tests/test_text_family_adapters.py`
- script: `scripts/text_family_config_probe.py`

The probe now also emits `metadata_copy_calls_mean` so CI can detect regressions in the metadata mapping fast path.

## Success Criteria

- Focused text-family adapter tests pass.
- Changed-scope coverage for the touched Python files remains at least 95%.
- Registered probe completes successfully and reports `metadata_copy_calls_mean=0.0`.
