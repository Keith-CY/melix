#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from dataclasses import fields
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime import mlx_audio_runtime
from worker.runtime.audio_runtime_protocols import AudioRuntimeLoadedModel
from packages.protocol.python.worker.v1 import inference_pb2


class FakeChunk:
    def __init__(self) -> None:
        self.audio = [0.1, -0.1, 0.0]
        self.sample_rate = 24_000


class FakeTTSModel:
    def generate(self, text, voice=None, instruct=None, speed=1.0, verbose=False):
        _ = (text, voice, instruct, speed, verbose)
        yield FakeChunk()


def _loaded_model(model: FakeTTSModel) -> AudioRuntimeLoadedModel:
    kwargs = {
        "backend_id": "mlx_audio.tts",
        "family_id": "qwen3-tts",
        "runtime_name": "mlx-audio-tts",
        "model": model,
        "voice_mode": "hybrid",
        "supports_instructions": True,
        "output_formats": ("wav",),
    }
    field_names = {field.name for field in fields(AudioRuntimeLoadedModel)}
    if "generate_parameter_names" in field_names:
        kwargs["generate_parameter_names"] = tuple(mlx_audio_runtime.signature(model.generate).parameters)
    return AudioRuntimeLoadedModel(**kwargs)


def run_probe() -> dict[str, float]:
    iterations = int(os.environ.get("MELIX_MLX_AUDIO_SIGNATURE_PROBE_ITERATIONS", "5000"))
    sample_count = int(os.environ.get("MELIX_MLX_AUDIO_SIGNATURE_PROBE_SAMPLES", "5"))
    elapsed_samples: list[float] = []
    signature_call_samples: list[float] = []
    byte_count = 0
    original_signature = mlx_audio_runtime.signature

    for _ in range(sample_count):
        signature_calls = 0

        def tracked_signature(callable_obj):
            nonlocal signature_calls
            signature_calls += 1
            return original_signature(callable_obj)

        model = FakeTTSModel()
        mlx_audio_runtime.signature = tracked_signature
        try:
            loaded_model = _loaded_model(model)
            runtime = mlx_audio_runtime.MLXAudioSpeechRuntime()
            request = inference_pb2.SpeakRequest(
                input="signature cache probe",
                voice="alloy",
                instructions="Speak calmly.",
                format="wav",
            )
            signature_calls = 0
            started_at = time.perf_counter()
            for _index in range(iterations):
                result = runtime.speak(loaded_model, request)
                byte_count += len(result.audio_bytes)
            elapsed_samples.append((time.perf_counter() - started_at) * 1000.0)
            signature_call_samples.append(float(signature_calls))
        finally:
            mlx_audio_runtime.signature = original_signature

    if byte_count <= 0:
        raise RuntimeError("mlx-audio signature probe produced no audio bytes")

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "signature_calls_mean": statistics.fmean(signature_call_samples),
        "iterations_per_sample": float(iterations),
        "sample_count": float(sample_count),
        "audio_bytes_total": float(byte_count),
    }


def main() -> int:
    print(json.dumps(run_probe(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
