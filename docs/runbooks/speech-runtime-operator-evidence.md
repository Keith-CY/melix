# Speech Runtime Operator Evidence

Run the repository-owned `M17.4` smoke workflow when you need reproducible operator evidence for
the current speech-to-text and text-to-speech surface without reconstructing runtime-pack state,
managed-model state, or locale behavior by hand.

## Scope

The smoke covers four repository-owned live paths:

- one `Whisper`-class transcription request over `/v1/audio/transcriptions`
- one `Parakeet`-class transcription request over `/v1/audio/transcriptions`
- one `Kokoro`-class synthesis request over `/v1/audio/speech`
- one `Qwen3-TTS`-class synthesis request over `/v1/audio/speech`
- one `Qwen3-TTS` progressive synthesis request over `/v1/audio/speech` using the same
  prompt/voice pair as the buffered fallback path

The workflow starts a local Melix stack, installs fake `mlx_audio` backend fixtures into the
Python worker process, seeds runtime-pack plus managed-model manifests under a temporary app
support directory, and then exercises the real HTTP path. The smoke does not claim audio-quality
judgment or semantic speech-intelligence scoring. It records the current operator-visible runtime
behavior that Melix exposes today.

## Command

Run the canonical smoke command from the repository root:

```bash
make phase17-metrics
```

For direct JSON output without the Make target wrapper:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx \
python scripts/m17_speech_runtime_smoke.py --json
```

## Output

The payload includes:

- `checks`
  - `speech.transcription.whisper_success`
  - `speech.transcription.parakeet_success`
  - `speech.synthesis.kokoro_success`
  - `speech.synthesis.qwen3_tts_success`
  - `speech.synthesis.qwen3_tts_locale_resolution_success`
  - `speech.synthesis.qwen3_tts_instruction_path_success`
  - `speech.synthesis.qwen3_tts_streaming_success`
  - `speech.synthesis.qwen3_tts_streaming_playable_wav_success`
  - `speech.synthesis.qwen3_tts_streaming_parity_success`
  - `speech.synthesis.qwen3_tts_streaming_buffered_fallback_success`
  - `speech.synthesis.qwen3_tts_streaming_ttfa_reduction_success`
- `metrics`
  - `speech.integration_success_rate`
  - per-family request latency for `Whisper`, `Parakeet`, `Kokoro`, and `Qwen3-TTS`
  - transcription duration, preprocess latency, and chunk count for the STT families
  - synthesis output bytes for the TTS families
  - `speech.synthesis.qwen3_tts.voice_fallback_count`
  - `speech.synthesis.qwen3_tts.locale_header_success_rate`
  - `speech.synthesis.qwen3_tts.streaming_first_audio_latency_ms`
  - `speech.synthesis.qwen3_tts.streaming_buffered_latency_ms`
  - `speech.synthesis.qwen3_tts.streaming_ttfa_reduction_pct`
  - `speech.synthesis.qwen3_tts.streaming_malformed_wav_count`
- `scenarios`
  - per-family raw evidence including response excerpts, locale headers, fallback counters, and
    output-size evidence

## Interpretation

Use the smoke output to answer these operator questions:

- Can Melix still lazy-load managed `mlx_audio` speech families through the real HTTP path?
- Are `Whisper` and `Parakeet` still publishing transcription latency plus chunk-count evidence?
- Does `Kokoro` still expose stable English locale metadata and produce WAV bytes?
- Does `Qwen3-TTS` still resolve explicit locales through the request-driven locale policy and keep
  the instruction path separate from voice-descriptor fallback?
- Does the progressive `Qwen3-TTS` path emit playable WAV bytes, preserve a buffered fallback for
  the same prompt/voice pair, and reduce time-to-first-audio by at least 50 percent?

The `whisper` and `parakeet` scenario entries are the canonical source for:

- backend-family-specific transcription response evidence
- `audio.preprocess_latency_ms`
- `audio.transcription_latency_ms`
- `audio.audio_chunk_count`
- `audio.language_fallback_count`

The `kokoro` and `qwen3_tts` scenario entries are the canonical source for:

- `audio.speech_latency_ms`
- `audio.speech_output_bytes`
- `audio.voice_fallback_count`
- `audio.speech_streaming_enabled`
- `audio.speech_streaming_interval_ms`
- `audio.speech_first_audio_latency_ms`
- locale header evidence such as requested locale, resolved locale, locale source, and locale
  policy

The `qwen3_tts_streaming` scenario is the canonical source for:

- streamed first-audio latency versus the same prompt/voice buffered fallback latency
- progressive WAV playability evidence
- streaming/non-streaming parity for the same prompt/voice pair
- malformed progressive WAV count
- streamed chunk count and stream interval evidence

## Diagnosis

If transcription requests fail with `audio_runtime_pack_required`:

- inspect the seeded runtime-pack manifest under the temporary app-support root
- confirm the failing model still advertises `melix.audio.install_profile = audio-stt`

If transcription requests fail with `audio_model_download_required`:

- inspect `.melix-managed-audio-models.json`
- confirm the managed model root still contains a `managed-model.json` entry for the failing model

If transcription or synthesis first-load requests fail with `audio_processor_validation_failed`:

- inspect the HTTP error `details`
- confirm `missing_asset_class` is `processor_config`
- confirm `load_stage` identifies `load_model:processor_asset_preflight`
- confirm `audio_processor_validation_result` is `0`
- inspect the managed model directory and verify it contains one of `processor_config.json`,
  `preprocessor_config.json`, or `feature_extractor_config.json`
- redownload or reinstall the managed audio model before retrying the request

If synthesis locale evidence regresses:

- inspect `requested_locale`
- inspect `resolved_locale`
- inspect `locale_source`
- inspect `locale_policy`
- inspect `supported_locales`

If `Qwen3-TTS` starts reporting fallback behavior unexpectedly:

- inspect `speech.synthesis.qwen3_tts.voice_fallback_count`
- inspect `speech.synthesis.qwen3_tts_instruction_path_success`
- compare the request payload in the smoke script against the advertised `voice_mode = hybrid`
  contract in the support matrix

If progressive speech streaming regresses:

- inspect `speech.synthesis.qwen3_tts.streaming_ttfa_reduction_pct`; it should be at least `50.0`
- inspect `speech.synthesis.qwen3_tts.streaming_malformed_wav_count`; it should be `0.0`
- inspect `qwen3_tts_streaming.response_excerpt`; it should begin with a RIFF/WAVE header
- inspect `audio.speech_streaming_enabled`, `audio.speech_streaming_interval_ms`, and
  `audio.speech_first_audio_latency_ms` in the metrics export

If support-matrix status drifts from the smoke:

- re-run `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python python -m worker.productization.family_support_matrix`
- confirm the four speech-family rows still point at
  `tests/integration/test_m17_speech_runtime_smoke.py::test_m17_speech_runtime_smoke_records_live_audio_operator_evidence`

## Verification

The repository-owned verification entry points for this surface are:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python --extra mlx pytest \
  services/mlx-worker-python/tests/test_acceptance_metrics.py \
  tests/integration/test_m17_speech_runtime_smoke.py \
  tests/integration/test_non_text_endpoints.py -q
```

These checks prove both the machine-readable report contract and the live speech smoke workflow.
