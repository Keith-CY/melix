# VLM Text Chat Routing Repair

## Goal

Allow VLM models that advertise both `text` modality and `generate` task support
to serve text-only chat through the existing CLI and OpenAI-compatible streaming
APIs.

## Context

Gemma 4 MLX packages are discovered as `model_kind: "vlm"` and route through
`python_vlm` / `mlx_vlm`. The Python worker can load these models and generate
from text-only prompts, but the control-plane chat path currently calls
`ensureTextModelReady`, which rejects non-`text` capability classes before the
request reaches the worker.

## Scope

- Update the text serving readiness gate so text-generating VLM summaries pass.
- Keep embeddings, rerank, OCR-only, image, speech, and transcription models out
  of the text chat path.
- Cover the loader and HTTP gateway paths with focused Swift tests.
- Verify with the downloaded `mlx-community/gemma-4-26b-a4b-it-4bit` model when
  local runtime resources allow it.

## Performance Probes

- Preserve existing first-load probes:
  `control_plane.text_first_load_ms`,
  `control_plane.text_first_load_estimated_resident_bytes`, and
  `control_plane.text_first_load_resident_bytes`.
- Preserve routing latency probe: `control_plane.worker_route_ms`.
- Success metric: text-only VLM chat requests reach the Python VLM worker and
  stream at least one token through `/v1/chat/completions`, `/v1/responses`, and
  `melix chat run`.

## Verification

- `swift test --package-path services/control-plane-swift --filter 'OnDemandModelLoaderTests|OpenAIHandlerTests'`
- `swift test --package-path services/control-plane-swift`
- `git diff --check`
- Local smoke:
  - `melix chat run --model-id mlx-community/gemma-4-26b-a4b-it-4bit ...`
  - `POST /v1/chat/completions`
  - `POST /v1/responses`

## Metrics

- Runtime throughput metrics: use local smoke token output as qualitative
  evidence for this routing repair; no decode algorithm changes are expected.
- Coverage target: focused Swift coverage for loader and HTTP gateway changed
  lines.
