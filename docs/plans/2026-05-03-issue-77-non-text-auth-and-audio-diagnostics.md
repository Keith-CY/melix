# Issue 77 Non-Text Auth and Audio Diagnostics

## Goal

Make non-text and tool/control gateway requests fail safely by enforcing the shared gateway
authorization boundary on every operator-facing route, rejecting endpoint/model mismatches before
worker execution, and surfacing actionable audio processor asset diagnostics during first load.

## Scope

- Add an operator route admission fixture matrix that covers text, non-text, image, audio,
  tool/control, cache, model, and unknown routes under shared API-key mode.
- Centralize endpoint-family validation for text generation, embeddings, rerank, transcription,
  speech, and image endpoints before request execution reaches the worker.
- Validate required `mlx_audio` processor assets at first load for speech and transcription models.
- Expose operator-visible metrics for blocked auth, wrong-endpoint validation, and audio processor
  validation failures.

## Non-Goals

- Redesign the gateway auth product surface.
- Change model download, packaging, or scheduler behavior outside the endpoint admission contract.
- Add new audio model families.

## Implementation Plan

- [x] Add focused Swift HTTP gateway tests proving every operator-facing route except `/health`
  inherits the configured shared API-key policy.
- [x] Add a shared endpoint contract helper in `OpenAIHandler` that resolves selected model
  metadata and rejects mismatches with a structured 400 error before worker dispatch.
- [x] Record `route_auth_policy` and `endpoint_type_validation_result` metrics on the changed
  gateway paths.
- [x] Add Python audio runtime validation for required processor assets and return
  `audio_processor_validation_failed` with missing asset class and `load_model` stage details.
- [x] Add regression fixtures for missing audio processor configs, wrong endpoint selection, and
  auth-blocked non-text/tool requests.
- [x] Update runbook evidence for the new diagnostics.

## Performance And Metrics

- `route_auth_policy`: numeric auth mode projection recorded for every non-health request.
- `endpoint_type_validation_result`: `1` for accepted endpoint/model pair, `0` for rejected pair.
- `audio_processor_validation_result`: worker error detail set to `0` when required real
  `mlx_audio` processor assets are missing. Successful validation continues into the existing load
  path and is represented by successful load evidence rather than a separate success receipt.
- Existing latency probes remain unchanged: the validation runs before worker execution and should
  avoid creating new request latency on successful deterministic routes beyond metadata lookup.

## Verification

- `swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests'`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_service.py -q`
- `git diff --check`

## Metrics Report

- Swift gateway regression: `OpenAIHandlerTests` passed with 122 tests. The auth parity fixture
  covers 16 operator-facing non-health routes, with 14 shared-policy failures returning
  `missing_api_key`, 2 session-token failures returning `missing_session`, and `/health` remaining
  open.
- Endpoint validation regression: 7 wrong-endpoint fixtures returned structured
  `wrong_endpoint_for_model` 400 responses, recorded
  `endpoint_type_validation_rejection_count = 7`, and did not dispatch to worker clients.
- Python audio regression: 39 targeted audio/runtime tests passed. The missing processor fixture
  covers both `mlx_audio.stt` and `mlx_audio.tts`; worker first-load errors return
  `audio_processor_validation_failed` with `missing_asset_class`,
  `load_stage = load_model:processor_asset_preflight`, and
  `audio_processor_validation_result = 0`.
- Coverage percentage: N/A for this handoff because the touched-scope verification commands do not
  emit line coverage. The regression counts above are the measured automated evidence for this
  slice.
