from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import inference_pb2
from worker.model_registry.catalog import WorkerModelCatalog
from worker.runtime import runtime_utils
from worker.runtime.mlx_audio_runtime import MLXAudioSpeechRuntime


class _FakeChunk:
    def __init__(self, audio: list[float]) -> None:
        self.audio = audio
        self.sample_rate = 24_000


class _FakeTTSModel:
    def generate(self, text, voice=None, instruct=None, verbose=False):
        _ = text
        _ = voice
        _ = instruct
        _ = verbose
        yield _FakeChunk([0.05, -0.05, 0.0, 0.025])


def _install_fake_mlx_audio() -> None:
    mlx_audio = ModuleType("mlx_audio")
    mlx_audio_tts = ModuleType("mlx_audio.tts")
    mlx_audio_tts_utils = ModuleType("mlx_audio.tts.utils")

    def load_model(model_path: str, strict: bool = True):
        _ = model_path
        _ = strict
        return _FakeTTSModel()

    mlx_audio_tts_utils.load_model = load_model
    sys.modules["mlx_audio"] = mlx_audio
    sys.modules["mlx_audio.tts"] = mlx_audio_tts
    sys.modules["mlx_audio.tts.utils"] = mlx_audio_tts_utils


def main() -> None:
    _install_fake_mlx_audio()
    runtime = MLXAudioSpeechRuntime()

    original_signature = runtime_utils.inspect.signature
    signature_calls = 0

    def tracked_signature(callable_obj):
        nonlocal signature_calls
        signature_calls += 1
        return original_signature(callable_obj)

    runtime_utils.inspect.signature = tracked_signature
    try:
        runtime_utils.clear_callable_kwarg_signature_cache()
        loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())
        request = inference_pb2.SpeakRequest(
            input="signature reuse probe",
            voice="alloy",
            instructions="Speak crisply.",
            format="wav",
        )
        samples: list[float] = []
        per_request_signature_calls: list[float] = []
        output_bytes_total = 0
        speak_call_count = int(
            os.environ.get("MELIX_AUDIO_SPEECH_SIGNATURE_PROBE_CALLS", "750")
        )
        sample_count = int(
            os.environ.get("MELIX_AUDIO_SPEECH_SIGNATURE_PROBE_SAMPLES", "5")
        )
        for _sample_index in range(sample_count):
            before_calls = signature_calls
            started = time.perf_counter()
            for _ in range(speak_call_count):
                result = runtime.speak(loaded, request)
                output_bytes_total += len(result.audio_bytes)
            samples.append((time.perf_counter() - started) * 1000.0)
            per_request_signature_calls.append(float(signature_calls - before_calls))
    finally:
        runtime_utils.inspect.signature = original_signature
        runtime_utils.clear_callable_kwarg_signature_cache()

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(samples),
                "inspect_signature_calls_mean": statistics.fmean(per_request_signature_calls),
                "speak_call_count": float(speak_call_count),
                "sample_count": float(sample_count),
                "output_bytes_total": float(output_bytes_total),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
