# Vision Family Config Slots Performance Slice

## Goal

Reduce Python object overhead on the registered vision-family prompt token counting path by making the immutable vision-family configuration dataclasses slotted.

## Affected Path

- `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`
- `services/mlx-worker-python/tests/test_vision_runtime.py`
- `scripts/vision_family_prompt_token_count_probe.py`

The affected path is covered by the registered PR-scoped probe `vision-family-prompt-token-count-scan` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries. This slice extends the same probe to emit `config_object_footprint_bytes` so the slot-backed configuration-object memory effect is measured directly in addition to the existing token-count hot-path metrics.

## Implementation Slice

- Add `slots=True` to `VisionFamilyDescriptor`, `ResolvedVisionFamilyConfig`, and `VisionFamilyAdapter`.
- Preserve frozen dataclass semantics and existing prompt token counting behavior.
- Add focused regression coverage that the hot-path configuration objects remain slot-backed.

## Validation

Linux-local validation for this Python slice:

- Focused vision runtime pytest and PR-scoped probe registry tests.
- Changed-scope coverage using the registered probe coverage command.
- Registered `vision-family-prompt-token-count-scan` probe.

GitHub Actions must complete the PR-scoped performance workflow before merge.
