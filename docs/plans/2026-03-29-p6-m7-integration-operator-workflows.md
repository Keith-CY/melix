# P6-M7 Integration and Operator Workflows Implementation Plan

**Goal:** Leave Phase 6 with a reproducible multimodal operator workflow that exercises OCR, VLM, transcription, and speech through the live stack, exports non-`N/A` latency and preprocessing metrics, and records text responsiveness under concurrent multimodal load.

**Scope:** This milestone covers a Phase 6 metrics report script, a `make phase6-metrics` command, multimodal integration smoke that reads live metrics exports, deterministic load controls for reproducible operator evidence, and a dedicated Phase 6 runbook for stack boot, smoke, metrics capture, and recovery. It does not add new public endpoints or desktop panels.

## Context

- Phase plan: `docs/plans/2026-03-27-phase-6-vision-ocr-audio-transcription.md`
- Milestone ladder: `docs/plans/2026-03-28-post-phase-0-coding-milestones.md`
- Relevant code:
  - `tests/integration/*`
  - `tests/integration/helpers.py`
  - `scripts/dev_up.sh`
  - `scripts/dev_down.sh`
  - `services/control-plane-swift/Sources/HTTPGateway/*`
  - `services/control-plane-swift/Sources/EnginePool/*`
  - `services/mlx-worker-python/worker/runtime/*`

## Non-Goals

- Add new multimodal worker classes or new public API families.
- Build the Image panel or any Phase 7 image-generation workflow.
- Replace the existing Phase 6 Chat panel runbook.
- Add remote telemetry export, dashboards, or cloud-only operator dependencies.

## Performance Probes

- `vision.ocr_latency_ms`
- `vision.vlm_first_token_ms`
- `vision.preprocess_latency_ms`
- `vision.preprocess_peak_memory_bytes`
- `audio.transcription_latency_ms`
- `audio.speech_latency_ms`
- `audio.audio_duration_seconds`
- `audio.audio_chunk_count`
- `audio.speech_output_bytes`
- `scheduler.multimodal_queue_delay_ms`
- `scheduler.text_ttft_under_multimodal_ms`

## Work Plan

### Task 1: Add deterministic operator-load controls for multimodal runtimes

- Add narrow deterministic delay controls for OCR, VLM, transcription, and speech runtime paths.
- Keep the controls opt-in and environment-driven so default CI behavior stays fast.
- Make the live integration stack able to pass environment overrides into worker processes.

### Task 2: Add live multimodal smoke coverage tied to metrics exports

- Add integration smoke that exercises OCR, VLM, transcription, and speech through the live stack.
- Assert that metrics exports contain real latency and preprocessing values after the smoke completes.
- Add a live interference case where text runs while a delayed multimodal request is active and assert that `scheduler.text_ttft_under_multimodal_ms` is recorded.

### Task 3: Add the Phase 6 metrics report command

- Add `make phase6-metrics`.
- Implement `scripts/phase6_metrics_report.py` to:
  - boot the live stack
  - run OCR, VLM, transcription, speech, and text-under-multimodal-load probes
  - print a compact report with latency, preprocessing, memory, and interference values
- Keep the deterministic path as the default reproducible benchmark mode.

### Task 4: Add the operator runbook and docs wiring

- Add a dedicated Phase 6 runbook for multimodal stack boot, smoke reproduction, metrics capture, and shutdown.
- Update docs indexes so the milestone plan, runbook, and metrics command are discoverable.
- Keep the runbook aligned with `scripts/dev_up.sh`, `scripts/dev_down.sh`, and `make phase6-metrics`.

## Verification

```bash
make swift-test
make py-test
make integration-test
make coverage
make phase6-metrics
git diff --check
```

## Acceptance

- The live stack can reproduce OCR, VLM, transcription, and speech flows without manual patching.
- The Phase 6 metrics report contains non-`N/A` latency and preprocessing numbers for OCR, VLM, transcription, speech, and text-under-multimodal-load.
- The touched scope remains at or above `95%` measured coverage where coverage is currently measurable.
