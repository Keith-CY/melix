# Text Family Model Type Reuse Fast Path

## Scope

This Python-only performance slice is limited to `text_family_adapters.detect_text_family_identity()` during repeated text-family config resolution for configs that already expose a top-level `model_type`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/text_family_config_probe.py`

## Change

`detect_text_family_identity()` now reuses the normalized top-level `model_type` discovered while resolving the architecture instead of calling a second helper that reads the same mapping key again. The fallback paths for architecture-list detection, nested `text_config.model_type`, explicit family overrides, and directory-name inference remain unchanged.

The direct `_detected_architecture()` helper remains specialized for explicit-family resolution so existing metadata-override probe workloads do not pay tuple construction overhead from the no-override helper.

## Validation Plan

1. Add a focused regression test proving top-level `model_type` detection performs one mapping key access.
2. Run the registered focused pytest command for `text-family-config-copy-elision` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run `scripts/text_family_config_probe.py` against the `origin/main` baseline and this branch and compare `elapsed_ms_mean`, `peak_bytes_mean`, `config_copy_calls_mean`, and `config_key_accesses_mean`.
5. Use the PR-scoped performance workflow as the final CI merge gate before squash merging.

## Metrics

Success is measured by preserving `config_key_accesses_mean`, keeping `config_copy_calls_mean == 0`, and avoiding `elapsed_ms_mean` regression in `scripts/text_family_config_probe.py`; the focused regression test covers the one-lookup no-override fast path directly. This slice has no Swift runtime effect.
