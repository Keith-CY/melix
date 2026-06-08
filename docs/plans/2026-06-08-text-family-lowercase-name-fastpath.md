# Text Family Lowercase Name Fast Path

## Scope

This slice keeps text-family config resolution behavior unchanged while reducing
per-resolution string normalization work for already-normalized model family
names.

## Registered Probe

The affected path is already covered by the PR-scoped registered probe
`text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries for:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `scripts/text_family_config_probe.py`

## Change

`detect_text_family_identity()` now checks exact explicit family IDs before
falling back to `strip().lower()`, and `_detected_architecture()` / `_model_type()`
return already-lowercase model names without allocating a lowercased copy.
Fallback normalization remains in place for mixed-case, whitespace-padded, and
unsupported explicit inputs.

## Validation Plan

- Add focused regression tests proving exact family IDs and lowercase
  `model_type` values avoid normalization allocation.
- Run the registered text-family tests and PR-scoped probe locally on Linux.
- Use the PR-scoped performance workflow as the merge gate for base/head probe
  validation.
