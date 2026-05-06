from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

REPO_ROOT = Path.cwd()
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import inference_pb2
from worker.model_registry.catalog import WorkerModelCatalog
import worker.runtime.mlx_audio_runtime as mlx_audio_runtime


def _install_fake_mlx_audio() -> None:
    mlx_audio = ModuleType("mlx_audio")
    mlx_audio_tts = ModuleType("mlx_audio.tts")
    mlx_audio_tts_utils = ModuleType("mlx_audio.tts.utils")

    class FakeTTSModel:
        def generate(self, text, voice=None, instruct=None, verbose=False):
            if voice != "alloy" or instruct != "Speak calmly." or verbose is not False:
                raise RuntimeError("unexpected speech kwargs")
            yield SimpleNamespace(audio=[0.1, -0.1, 0.0], sample_rate=24_000)

    def fake_load_model(model_path: str, strict: bool = True):
        _ = model_path
        _ = strict
        return FakeTTSModel()

    mlx_audio_tts_utils.load_model = fake_load_model
    sys.modules["mlx_audio"] = mlx_audio
    sys.modules["mlx_audio.tts"] = mlx_audio_tts
    sys.modules["mlx_audio.tts.utils"] = mlx_audio_tts_utils


def main() -> None:
    _install_fake_mlx_audio()
    original_signature = mlx_audio_runtime.signature
    sample_count = int(os.environ.get("MELIX_MLX_AUDIO_SIGNATURE_PROBE_SAMPLES", "5"))
    iterations = int(os.environ.get("MELIX_MLX_AUDIO_SIGNATURE_PROBE_ITERATIONS", "4000"))
    elapsed_samples: list[float] = []
    signature_call_samples: list[float] = []
    output_sizes: list[float] = []

    for _sample in range(sample_count):
        signature_calls = 0

        def tracked_signature(callable_object):
            nonlocal signature_calls
            signature_calls += 1
            return original_signature(callable_object)

        mlx_audio_runtime.signature = tracked_signature
        runtime = mlx_audio_runtime.MLXAudioSpeechRuntime()
        loaded = runtime.load_model(WorkerModelCatalog.mlx_qwen3_tts_model())
        request = inference_pb2.SpeakRequest(
            input="probe speech",
            voice="alloy",
            instructions="Speak calmly.",
            format="wav",
        )
        started = time.perf_counter()
        total_output_bytes = 0
        for _index in range(iterations):
            result = runtime.speak(loaded, request)
            total_output_bytes += len(result.audio_bytes)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        signature_call_samples.append(float(signature_calls))
        output_sizes.append(float(total_output_bytes))

    mlx_audio_runtime.signature = original_signature
    print(
        json.dumps(
            {
                "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
                "inspect_signature_calls_mean": round(statistics.fmean(signature_call_samples), 6),
                "iterations_per_sample": float(iterations),
                "sample_count": float(sample_count),
                "output_bytes_mean": round(statistics.fmean(output_sizes), 6),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
