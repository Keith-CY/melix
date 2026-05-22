# Text family slotted config records

## Goal

Reduce per-resolution Python object overhead on the text-family configuration path by making the immutable text-family dataclasses slotted. This keeps behavior unchanged while avoiding per-instance `__dict__` allocation for descriptors, detection records, and resolved runtime configs.

## Registered probe

The affected path is covered by the registered PR-scoped probe `text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry already provides focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/text_family_config_probe.py`

The probe reports elapsed time, peak bytes, and config copy attempts across repeated `resolve_text_family_config(...)` calls.

## Slice

- Add `slots=True` to the frozen text-family dataclasses.
- Add a regression test proving the public dataclass instances no longer expose `__dict__` while preserving existing resolution behavior.
- Do not change config parsing, routing decisions, metadata keys, or probe semantics.

## Verification

Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.
