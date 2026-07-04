# Text Family Metadata Override Lazy Hints

## Goal

Reduce repeated Python mapping access during `resolve_text_family_config(...)` when
metadata already supplies authoritative text-family runtime hints.

## Scope

This Python-only performance slice is limited to:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/text_family_config_probe.py`
- `infra/perf/pr_scoped_probes.json`

The registered PR-scoped probe remains `text-family-config-copy-elision`. This
slice extends that probe to include `config_key_accesses_mean` so CI and local
runs can validate that metadata override paths skip unnecessary config hint
lookups.

## Behavior

When metadata provides these keys:

- `melix.text.attention_profile`
- `melix.text.rope_profile`
- `melix.text.moe.gate_dequant`

`resolve_text_family_config(...)` now uses the metadata values directly instead
of eagerly evaluating the corresponding config inference fallbacks. Family
detection and expert-count precedence still read the config payload as before,
so resolution semantics remain unchanged.

## Validation

Run the registered focused test command, changed-scope coverage command, and
probe command for the text-family config probe before opening the PR. The probe
reports elapsed time, peak bytes, config copy calls, and config key accesses.
