# Text Family Attention Hint Lookup Fast Path

## Scope

Optimize `text_family_adapters._inferred_attention_profile()` for repeated text-family
config resolution.

## Probe Coverage

The affected path is already registered in `infra/perf/pr_scoped_probes.json` as
`text-family-config-copy-elision`, with focused `test_command`, `coverage_command`,
and `probe_command` entries covering:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `scripts/text_family_config_probe.py`

## Change

Use direct mapping lookups with `KeyError` handling for optional attention hint keys
instead of repeated `Mapping.get()` calls followed by `_string(...).lower()` on
missing values. This preserves MLA string hint detection and the existing `use_mla`
boolean fallback while reducing repeated optional-key overhead in the registered
config-resolution probe.

## Verification Plan

1. Run focused text-family tests and PR-scoped performance registry tests.
2. Run changed-scope coverage through the registered probe command.
3. Run `scripts/text_family_config_probe.py` on `origin/main` and this branch, at
   least three times each, and compare `elapsed_ms_mean`, `peak_bytes_mean`, and
   `config_copy_calls_mean`.
4. Accept the slice only if the registered probe shows a clear non-regressing
   direction and behavior coverage stays at 95%+ for changed lines.
