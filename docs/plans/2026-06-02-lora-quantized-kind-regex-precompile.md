# LoRA Quantized Kind Regex Precompile Slice

## Goal

Reduce repeated regex setup in LoRA runtime metadata quantized-base detection.
The hot path parses profile IDs, extension values, and model identity text to
identify quantized base kinds such as `4bit`, `8bit`, `q4`, `q8`, and `optiq`.

## Scope

- Path: `services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py`
- Replace per-call `re.search(...)` pattern construction in
  `_quantized_kind_from_text(...)` with module-level compiled regex patterns.
- Preserve the existing token-boundary behavior for accepted quantized kind
  strings and false positives such as `not-a-q4suffix`.
- Extend the existing `lora-aux-modules-scandir` PR-scoped probe because it is
  already the registered probe for `lora_runtime_metadata.py`.

## Probe

Registered probe: `lora-aux-modules-scandir`

The probe keeps its existing auxiliary-module scandir metrics and adds a
quantized-kind parser workload:

- `quantized_kind_baseline_elapsed_ms_mean` (dynamic `re.search` baseline)
- `quantized_kind_optimized_elapsed_ms_mean` (current module implementation)
- `quantized_kind_delta_ms` (optimized minus baseline; lower is better)
- `quantized_kind_iteration_count` (input scale)

The probe command runs the head probe script against the current repository root
when comparing base and head, so the same measurement code can validate both the
old and optimized implementations.

## Verification Plan

1. Focused regression test proving `_quantized_kind_from_text(...)` no longer
   calls `re.search(...)` at runtime while preserving positive and negative
   matching behavior.
2. Registered focused test command from `infra/perf/pr_scoped_probes.json`.
3. Registered changed-scope coverage command from the probe entry.
4. Registered probe locally on Linux before opening the PR.
5. PR-scoped performance workflow in GitHub Actions before merge.

## Linux Boundary

This slice changes Python worker metadata code and is locally verifiable on
Linux. No Swift/macOS-only runtime effect is claimed for this slice.
