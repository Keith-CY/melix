from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "m17_speech_runtime_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m17_speech_runtime_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m17_speech_runtime_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m17_speech_runtime_smoke)


def test_m17_speech_runtime_smoke_records_live_audio_operator_evidence() -> None:
    payload = m17_speech_runtime_smoke.run_smoke(Path(__file__).resolve().parents[2])

    assert payload["ok"] is True
    checks = payload["checks"]
    assert checks["speech.transcription.whisper_success"] is True
    assert checks["speech.transcription.parakeet_success"] is True
    assert checks["speech.synthesis.kokoro_success"] is True
    assert checks["speech.synthesis.qwen3_tts_success"] is True
    assert checks["speech.synthesis.qwen3_tts_locale_resolution_success"] is True
    assert checks["speech.synthesis.qwen3_tts_instruction_path_success"] is True
    assert checks["speech.synthesis.qwen3_tts_streaming_success"] is True
    assert checks["speech.synthesis.qwen3_tts_streaming_playable_wav_success"] is True
    assert checks["speech.synthesis.qwen3_tts_streaming_parity_success"] is True
    assert checks["speech.synthesis.qwen3_tts_streaming_buffered_fallback_success"] is True
    assert checks["speech.synthesis.qwen3_tts_streaming_ttfa_reduction_success"] is True

    metrics = payload["metrics"]
    assert metrics["speech.integration_success_rate"] == 100.0
    assert metrics["speech.transcription.whisper.chunk_count"] >= 1.0
    assert metrics["speech.transcription.parakeet.chunk_count"] >= 1.0
    assert metrics["speech.synthesis.kokoro.output_bytes"] > 0.0
    assert metrics["speech.synthesis.qwen3_tts.output_bytes"] > 0.0
    assert metrics["speech.synthesis.qwen3_tts.locale_header_success_rate"] == 100.0
    assert metrics["speech.synthesis.qwen3_tts.streaming_first_audio_latency_ms"] > 0.0
    assert metrics["speech.synthesis.qwen3_tts.streaming_buffered_latency_ms"] > 0.0
    assert metrics["speech.synthesis.qwen3_tts.streaming_ttfa_reduction_pct"] >= 50.0
    assert metrics["speech.synthesis.qwen3_tts.streaming_malformed_wav_count"] == 0.0

    scenarios = payload["scenarios"]
    assert "whisper transcription" in scenarios["whisper"]["response_excerpt"]
    assert scenarios["parakeet"]["language_fallback_count"] == 1.0
    assert scenarios["kokoro"]["resolved_locale"] == "en"
    assert scenarios["qwen3_tts"]["requested_locale"] == "en-us"
    assert scenarios["qwen3_tts"]["resolved_locale"] == "en"
    assert scenarios["qwen3_tts"]["locale_source"] == "request"
    assert scenarios["qwen3_tts"]["voice_fallback_count"] == 0.0
    assert scenarios["qwen3_tts_streaming"]["ttfa_reduction_success"] is True
    assert scenarios["qwen3_tts_streaming"]["parity_success"] is True
    assert scenarios["qwen3_tts_streaming"]["malformed_progressive_wav_count"] == 0.0
