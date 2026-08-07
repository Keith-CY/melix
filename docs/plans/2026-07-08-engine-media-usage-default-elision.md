# Engine media usage default elision performance slice

## Scope

This Python-only performance slice is limited to the standard text `EngineCore.generate()` finalization path in `services/mlx-worker-python/worker/engine/engine_core.py`.

The current no-usage path already avoids prompt-token fallback work, but it still builds a zero-valued media-feature usage mapping before request finalization. This slice keeps response metrics identical while deferring media-feature usage mapping construction until usage reporting actually needs a runtime media probe snapshot.

## Registered probe

The affected path is covered by the registered PR-scoped probe `engine-generate-usage-token-elision` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/engine_core.py`
- `services/mlx-worker-python/tests/test_generate_stream.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/engine_generate_usage_token_probe.py`

## Implementation plan

1. Extend the existing no-usage regression test so it proves `_media_feature_usage_from_probe()` is not called for `return_usage=False` text generation.
2. Replace eager zero media-usage mapping construction with a `None` sentinel in `EngineCore.generate()`.
3. Build the `TextFinalizationUsage` object without media keyword expansion when no media usage was collected, preserving zero-valued finalization metrics through dataclass defaults.
4. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate for the registered probe report.

## Validation boundary

This slice changes Python worker code only. Linux local validation covers focused Python tests, changed-scope coverage, and the registered performance probe. No Swift/macOS runtime effect is claimed for this slice.
