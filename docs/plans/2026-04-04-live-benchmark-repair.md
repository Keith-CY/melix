# Live Benchmark Repair For Gemma4 And Qwen3.5

## Summary

Repair the live benchmark path so Melix can produce fresh benchmark reports for:

- `unsloth/gemma-4-E4B-it-MLX-8bit`
- `Brooooooklyn/Qwen3.5-9B-unsloth-mlx`

The immediate failure boundary is in the Python maintenance bridge and the direct Hugging Face benchmark path. The repair must restore end-to-end benchmark execution, then save both final reports into `/tmp`.

## Execution Slices

1. Restore Python maintenance bridge command coverage.
   Add any missing maintenance commands required by the current control-plane worker client and cover them with regression tests.

2. Reproduce the direct Hugging Face benchmark failure with fresh local evidence.
   Capture the exact bridge-layer or worker-layer failure for `gemma-4-E4B-it-MLX-8bit` rather than treating control-plane `unavailable` as the root cause.

3. Fix the direct Hugging Face benchmark path.
   Ensure the imported-model benchmark request succeeds for both:
   - text-backed `gemma4` benchmark routing
   - text-generation MLX repos such as `Qwen3.5-9B-unsloth-mlx`

4. Verify with focused automated coverage.
   Run targeted Swift and Python tests for the touched bridge and benchmark paths before attempting final live proofs.

5. Run live proofs and save operator evidence.
   Produce fresh benchmark reports for both target repos and copy them into `/tmp` with stable filenames.

## Success Criteria

- `melix bench run --repo-id unsloth/gemma-4-E4B-it-MLX-8bit ...` succeeds
- `melix bench run --repo-id Brooooooklyn/Qwen3.5-9B-unsloth-mlx ...` succeeds
- both generated reports exist under `/tmp`
- touched-path automated coverage remains at least 95 percent before any commit
