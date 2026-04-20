# Milestone #43 · Phase 3B — Long-context chunked training + 25%/30% evidence gate

## Context

Issue [#43](https://github.com/Keith-CY/melix/issues/43) Phase 3 quantitative gate:

> improve long-context training tokens-per-second by at least 25 percent **or** reduce peak memory by at least 30 percent versus the current baseline path.

Phase 3A (PR [#50](https://github.com/Keith-CY/melix/pull/50)) shipped the measurement ruler — 4k and 8k long-context smoke fixtures plus a baseline-evidence harness. The committed baseline numbers (no chunking, `max_seq_length = target + 256`):

| Fixture | samples | tokens/sample | tokens/sec | peak_memory_gb |
| --- | --- | --- | --- | --- |
| long-context-4k.v1 | 10 | 4 073–4 128 | 0.176 | 7.85 |
| long-context-8k.v1 | 5 | 8 003–8 050 | 0.030 | 13.98 |

Gates on the same hardware generation:

- 4k: ≥ **0.220** tok/s OR ≤ **5.50** GB peak.
- 8k: ≥ **0.0375** tok/s OR ≤ **9.79** GB peak.

Phase 3B implements **Melix-side pre-chunking** at dataset-normalization time. Long samples are split into shorter training examples that each fit inside a reduced `max_seq_length`. Attention memory scales ~quadratically with sequence length, so halving `max_seq_length` (4256 → 2048) is the lever expected to clear the 30% peak-memory gate. The existing baseline training path stays intact and remains the default.

Phase 3C (separate plan) archives the comparative evidence bundle to the milestone.

## Scope

**In:**

- `worker/model_ops/training_dataset_chunker.py` — new module implementing `chunk_long_samples(samples, *, chunk_size, tokenizer) -> (chunked_samples, ChunkStats)`.
- `worker/model_ops/training_config.py` — new `ext` fields `chunked_training` (bool, default `false`) and `chunk_size` (int, default `max_seq_length`); surfaced on the frozen `LoRATrainingConfig`. `training_mode` stays `lora` / `qlora`.
- `worker/model_ops/mlx_lm_runner.py` — rewrites `train.jsonl` with chunked samples inside `train_native`, between tokenizer load and `load_local_dataset`. `TrainingMetrics` gains additive `chunked_enabled: bool`, `chunk_count: int`, `source_sample_count: int`; all three default to `False/0` so receipts/manifests stay forward-compatible. Surfaced in `asdict(result.metrics)`.
- `tests/test_training_dataset_chunker.py` — 9 unit cases (see `docs/plans/...` for the list).
- `tests/test_lora_long_context_chunked.py` — env-gated real-training harness (same gates as 3A) that runs at `chunk_size=2048` against each fixture, writes `chunked_evidence.json`, and **asserts the 25%/30% gate** vs the committed 3A baseline.
- `fixtures/training/long-context-4k.v1/chunked_evidence.json`, `fixtures/training/long-context-8k.v1/chunked_evidence.json` — committed after one local run on the Phase 3A hardware generation.

**Out:**

- Any Swift / control-plane / menubar change.
- Chunk overlap, semantic splitting, gradient checkpointing, sliding-window attention.
- Changes to training presets or defaults. `chunked_training=false` stays the default; existing jobs are bit-for-bit unchanged.
- Cross-turn context preservation in multi-turn chunking beyond per-turn emission.
- Phase 3C comparative evidence aggregation.

## Design

### Chunking algorithm

Given normalized chat `messages = [maybe(system), user_1, asst_1, (user_2, asst_2, ...)]` and target `chunk_size`:

1. **Full-sample fit check.** `tokenizer.apply_chat_template(messages, return_dict=False)` — same call pattern as `response_only_boundary.py`. If ≤ `chunk_size`, emit unchanged (1 chunk).
2. **Multi-turn overflow.** For samples with ≥2 (user, assistant) pairs: emit each `[maybe(system), user_i, assistant_i]` as its own chunk; prior-turn context is deliberately dropped. If any emitted pair still exceeds `chunk_size`, fall through to step 3 for that pair.
3. **Single-turn overflow.** Segment the user content by character count into K substrings such that each reconstructed chunk `[maybe(system), user_substring_i, assistant]` fits under `chunk_size`. Calibrate K by binary search on `len(user_content) // K` until the rendered length lands in `[chunk_size × 0.85, chunk_size]`. All K chunks share the same assistant message — deliberate; repeats gradient signal on the completion.
4. **Degenerate case.** If `[maybe(system), "", assistant]` alone exceeds `chunk_size`, raise `ModelOperationError("chunk_size_too_small", "Assistant message length {N} tokens exceeds chunk_size {M}")`. Preserves the Phase 2 response-only-boundary invariant: every emitted chunk is assistant-terminated with a computable boundary.
5. **Determinism.** Deterministic given `(sample, chunk_size, tokenizer)`. Idempotency unit test asserts `chunk(chunk(x)) == chunk(x)`.

### Integration seam

Chunking runs inside `MLXLMRunner.train_native`, after the MLX-LM tokenizer is loaded and before `load_local_dataset` reads `train.jsonl`. The helper reads `train.jsonl`, calls `chunk_long_samples`, and rewrites the file in-place. No-op when `config.chunked_training` is `False`. Chunk stats flow out via the runner's `TrainingMetrics`, not via the normalized-dataset snapshot manifest (which is a pre-training artifact and correctly describes the un-chunked input).

### Evidence harness

`test_lora_long_context_chunked.py` — same env-gating shape as the 3A harness (`MELIX_PHASE3_LONG_CONTEXT_EVIDENCE`, `MELIX_PHASE8_REAL_SMALL_MODEL_PATH`, plus `MELIX_PHASE3_LONG_CONTEXT_8K` for the 8k path). Each test:

1. Load fixture samples.
2. Build config with `chunked_training=true, chunk_size=2048, max_seq_length=2048`.
3. Run `MLXLMRunner().train_native(...)`.
4. Read committed `baseline_evidence.json` next to the fixture.
5. Write `chunked_evidence.json` with the chunked run's metrics + `source_baseline_reference`.
6. Assert `chunked.tokens_per_second >= baseline.tokens_per_second × 1.25` OR `chunked.peak_memory_gb <= baseline.peak_memory_gb × 0.70`.
7. Assert `chunk_count > sample_count` (chunking actually happened).
8. Assert `response_only_boundary_sample_count == chunk_count` (boundary computed for every emitted chunk).

## Critical files

```
services/mlx-worker-python/worker/model_ops/training_config.py          (+~30 lines)
services/mlx-worker-python/worker/model_ops/training_dataset.py         (+~20 lines)
services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py            (+~15 lines)
services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py (new, ~250 lines)
services/mlx-worker-python/tests/test_training_dataset_chunker.py       (new, ~200 lines)
services/mlx-worker-python/tests/test_lora_long_context_chunked.py      (new, ~170 lines)
services/mlx-worker-python/fixtures/training/long-context-4k.v1/chunked_evidence.json (new)
services/mlx-worker-python/fixtures/training/long-context-8k.v1/chunked_evidence.json (new)
docs/plans/2026-04-21-lora-long-context-chunked.md                      (new)
```

## Verification

1. `make py-test` — all existing tests stay green; 9 new unit tests run in CI; 2 new env-gated tests skip.
2. `MELIX_PHASE3_LONG_CONTEXT_EVIDENCE=1 MELIX_PHASE8_REAL_SMALL_MODEL_PATH=... pytest services/mlx-worker-python/tests/test_lora_long_context_chunked.py::test_phase3_long_context_chunked_4k -v` — produces 4k `chunked_evidence.json`, passes the 25%/30% gate.
3. Add `MELIX_PHASE3_LONG_CONTEXT_8K=1` for the 8k run on ≥20 GB hardware.
4. Re-run 3A harness `test_lora_long_context_baseline.py` — still green; baseline path untouched.
5. `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1 make phase8-real-e2e` — unchanged; 3B is additive + gated off.

## Evidence reported in PR body

- Test counts: 9 new unit tests (CI) + 2 new env-gated tests (skip by default).
- Committed 4k + 8k `chunked_evidence.json` contents.
- Diff table: baseline vs chunked tok/s + peak_memory_gb on same hardware.
- Explicit pass/fail statement on the 25%/30% gate per fixture.

## Risks

- **Chunk-boundary context loss** in multi-turn samples. Mitigated by scope: current fixtures fit under chunk_size after per-turn emission. Revisit if production datasets surface the need.
- **Tokenizer drift** between chunker and MLX-LM. Chunker reuses `apply_chat_template(return_dict=False)` — the Phase 2 cross-family-validated call pattern. Evidence records `mlx_lm_version`.
- **8k chunked wall time.** ~20 chunks × chunk_size=2048 expected in ~10–15 min on 64 GB Apple Silicon vs the 28 min baseline. Still gated out of CI.
- **Peak-memory probe accuracy.** `mx.metal.get_peak_memory()` undercounts deferred allocations. The 25% tok/s gate is the OR-branch backup if peak memory lands borderline.
- **Assistant-only overflow.** Handled with a clean `ModelOperationError`; our fixtures have assistant messages ≤ 40 tokens, nowhere near a 2048 chunk_size.
