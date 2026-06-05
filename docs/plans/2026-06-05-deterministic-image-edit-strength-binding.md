# Deterministic Image Edit Strength Binding

## Scope

Optimize one Python hot path in `DeterministicImageGenerationRuntime.edit_image(...)`: the generated image variant loop currently converts `request.strength` with `float(...)` on every variant even though the request strength is invariant for the whole edit request.

## Registered probe

The affected runtime path is covered by the registered PR-scoped probe `deterministic-image-output-byte-accounting` in `infra/perf/pr_scoped_probes.json`. The probe watches:

- `services/mlx-worker-python/worker/runtime/deterministic_image_generation_runtime.py`
- `services/mlx-worker-python/tests/test_image_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_image_output_bytes_probe.py`

That registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` fields. Local Linux verification uses that registered command set before PR creation; GitHub Actions PR-scoped performance remains the merge gate.

## Implementation

Bind `edit_strength = float(request.strength or 0.0)` once before the edit variant loop and pass the bound float into `_render_edit_payload(...)` for each generated edit artifact. This preserves the existing default/fallback behavior while avoiding redundant conversions in multi-variant deterministic image edits.

## Validation

1. Add a focused regression test that uses a float-counting request strength and proves the edit loop converts strength once across multiple variants.
2. Run the registered focused tests for `deterministic-image-output-byte-accounting`.
3. Run the registered changed-scope coverage command.
4. Run the registered probe locally and compare against a clean `origin/main` base worktree.
5. Use the PR-scoped performance workflow report as the merge gate after push.
