# Milestone #43 · Phase 3A — Long-Context Baseline Smoke Fixtures and Evidence Harness

## Context

Issue [#43](https://github.com/Keith-CY/melix/issues/43) Phase 3 is the "Long-context backend" slice of the LoRA fine-tuning milestone. It has two quantitative gates:

> - support repository-owned long-context smoke fixtures at 4k and 8k context windows without OOM on Apple Silicon
> - improve long-context tokens/sec by ≥25% OR reduce peak memory by ≥30% vs baseline

Phases 1 (PR [#45](https://github.com/Keith-CY/melix/pull/45), gradient_accumulation + resume surface) and 2 (PR [#49](https://github.com/Keith-CY/melix/pull/49), response_only_boundary observability) have merged.

Phase 3 splits cleanly into three shippable slices. This plan covers **Phase 3A** — the measurement ruler that Phase 3B must hit.

- **Phase 3A** (this plan): commit 4k + 8k long-context smoke fixtures and an env-gated baseline-evidence harness that records `tokens_per_second` + `peak_memory_gb` on today's unchunked training path.
- **Phase 3B** (separate plan): Melix-side pre-chunking of long samples so 4k/8k fixtures train without OOM and/or faster. Reuse 3A's harness to prove the 25%/30% gate.
- **Phase 3C** (separate plan): archive the comparative evidence bundle to the milestone issue.

Phase 4 (advanced alignment candidate scoring) stays out of scope.

## Scope

**In:**

- `fixtures/training/long-context-4k.v1/` — ~10 samples of ~4 000 Qwen tokens each, chat-messages format, assistant-terminated, mix of single/multi-turn and with/without system prompt.
- `fixtures/training/long-context-8k.v1/` — ~5 samples of ~8 000 Qwen tokens, same role variety.
- Fixture bodies are built from a committed public-domain paragraph repeated deterministically; reproducible offline.
- `tests/test_lora_long_context_baseline.py` — pytest harness that, when `MELIX_PHASE3_LONG_CONTEXT_EVIDENCE=1` AND `MELIX_PHASE8_REAL_SMALL_MODEL_PATH` are set, runs a tiny real LoRA training (`rank=8`, `batch_size=1`, `iters=5`, `response_only=True`) against each fixture and writes a committed `baseline_evidence.json`.
- Committed `baseline_evidence.json` files (one per fixture) with full `TrainingMetrics`.

**Out:**

- Any chunked-sequence implementation (Phase 3B).
- Any preset / `max_seq_length` default change.
- Any Swift control-plane or menubar change.
- The 25% / 30% quantitative gate — Phase 3B.

## Slices

### 3A-1 — Deterministic fixtures

- Public-domain seed paragraph committed inside the test module.
- A helper (module-local, not exported) concatenates the seed to reach target token counts under the Qwen chat template.
- Per-sample token counts pre-measured with the locally cached Qwen tokenizer and recorded in each fixture's `manifest.json`; the harness re-measures at run time and asserts drift stays within ±5 %.
- Samples MUST end with an assistant message (exercises the Phase 2 response-only-boundary path).

### 3A-2 — Measurement harness

- Two pytest tests: `test_phase3_long_context_baseline_4k`, `test_phase3_long_context_baseline_8k`.
- `skipif` gates: `MELIX_PHASE3_LONG_CONTEXT_EVIDENCE != "1"`, `MELIX_PHASE8_REAL_SMALL_MODEL_PATH` missing, locally cached Qwen3.5-0.8B-OptiQ-4bit tokenizer missing. 8k additionally gated by `MELIX_PHASE3_LONG_CONTEXT_8K=1` so 16 GB Apple Silicon can run 4k-only without OOM.
- Each test builds `TrainingRequest` + `LoRATrainingConfig` that point at the fixture, runs `MLXLMRunner().train_native(...)`, and writes `baseline_evidence.json` next to the fixture.
- Assertions: run completes, `examples_seen > 0`, `tokens_seen > 0`, evidence JSON schema present. **No throughput / memory pass/fail threshold** — this slice is the ruler, not the ruling.

### 3A-3 — Committed evidence schema

`baseline_evidence.json` (per fixture):

```json
{
  "schema_version": "melix.lora_long_context_baseline.v1",
  "fixture_id": "long-context-4k.v1",
  "sample_count": 10,
  "target_tokens_per_sample": 4000,
  "template_family": "qwen",
  "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
  "mlx_lm_version": "...",
  "generated_at_unix_ms": 1_776_660_000_000,
  "training_metrics": { ...TrainingMetrics.asdict... }
}
```

Committed once per hardware generation; Phase 3B will compare against these exact numbers.

## Critical files

```
services/mlx-worker-python/fixtures/training/long-context-4k.v1/manifest.json
services/mlx-worker-python/fixtures/training/long-context-4k.v1/samples.jsonl
services/mlx-worker-python/fixtures/training/long-context-4k.v1/baseline_evidence.json
services/mlx-worker-python/fixtures/training/long-context-8k.v1/...
services/mlx-worker-python/tests/test_lora_long_context_baseline.py
```

## Verification

1. `make py-test` — all existing tests stay green; new tests skip by default.
2. Locally: `MELIX_PHASE3_LONG_CONTEXT_EVIDENCE=1 MELIX_PHASE8_REAL_SMALL_MODEL_PATH=... pytest services/mlx-worker-python/tests/test_lora_long_context_baseline.py::test_phase3_long_context_baseline_4k -v` — completes in <120 s on M1/M2, produces the 4k evidence file.
3. With `MELIX_PHASE3_LONG_CONTEXT_8K=1` added: same for the 8k fixture on ≥20 GB unified memory hardware.
4. `MELIX_PHASE8_REAL_SMALL_MODEL_E2E=1 MELIX_PHASE8_REAL_SMALL_MODEL_PATH=... make phase8-real-e2e` — unchanged; Phase 3A is additive.

## Evidence reported in PR body

- Test counts: 2 new tests (both skip by default).
- Committed 4k + 8k `baseline_evidence.json` contents.
- Explicit note that the 25%/30% gate is **not** attempted here.

## Risks

- **8k OOM on 16 GB boxes.** Mitigated by independent env gate; the maintainer runs it on 24 GB+ hardware once and commits. CI never runs it.
- **Peak-memory probe accuracy.** `_mlx_peak_memory_gb()` reads `mx.metal.get_peak_memory()`; known to undercount on deferred allocations. Evidence records `mlx_lm_version` so Phase 3B comparisons stay apples-to-apples.
- **Fixture size.** Committed JSONL will be <200 KB per fixture after chat-template overhead.
- **MLX-LM API drift.** Harness uses public `train_native` + `load_local_dataset`. Same surface Phase 8 real-e2e already exercises.
