from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import inference_pb2  # noqa: E402
from worker.runtime.audio_runtime_protocols import AudioRuntimeLoadedModel  # noqa: E402
from worker.runtime.mlx_audio_runtime import MLXAudioTranscriptionRuntime  # noqa: E402

AUDIO_SIZE_BYTES = 8 * 1024 * 1024
SAMPLE_COUNT = 5


class FakeSTTModel:
    def generate(self, audio_path: str, **kwargs):
        path = Path(audio_path)
        if not path.is_file():
            raise AssertionError(f"missing audio path: {audio_path}")
        return SimpleNamespace(text="probe", language=kwargs.get("language") or "en", total_time=0.0)


def _measure_once(audio_path: Path) -> tuple[float, int, int, float]:
    runtime = MLXAudioTranscriptionRuntime()
    loaded = AudioRuntimeLoadedModel(
        backend_id="probe",
        family_id="probe",
        runtime_name=runtime.runtime_name,
        model=FakeSTTModel(),
        load_latency_ms=0.001,
    )
    request = inference_pb2.TranscribeRequest(audio_uri=audio_path.as_uri(), language="en", format="wav")
    original_read_bytes = Path.read_bytes
    original_exists = Path.exists
    read_count = 0
    exists_count = 0

    def counted_read_bytes(self: Path) -> bytes:
        nonlocal read_count
        if self == audio_path:
            read_count += 1
        return original_read_bytes(self)

    def counted_exists(self: Path) -> bool:  # pragma: no cover - covered on origin/main before elision.
        nonlocal exists_count
        if self == audio_path:
            exists_count += 1
        return original_exists(self)

    Path.read_bytes = counted_read_bytes
    Path.exists = counted_exists
    try:
        tracemalloc.start()
        started = time.perf_counter()
        result = runtime.transcribe(loaded, request)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        Path.read_bytes = original_read_bytes
        Path.exists = original_exists

    if result.text != "probe" or result.language != "en":
        raise AssertionError("unexpected transcription probe result")
    if runtime.last_probe_snapshot().preprocess_input_bytes != AUDIO_SIZE_BYTES:
        raise AssertionError("unexpected preprocess byte count")
    return elapsed_ms, read_count, exists_count, float(peak_bytes)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="melix-audio-uri-probe-") as tmp:
        audio_path = Path(tmp) / "large-local.wav"
        audio_path.write_bytes(b"a" * AUDIO_SIZE_BYTES)
        elapsed_samples: list[float] = []
        read_samples: list[float] = []
        peak_samples: list[float] = []
        exists_samples: list[float] = []
        for _ in range(SAMPLE_COUNT):
            elapsed_ms, read_count, exists_count, peak_bytes = _measure_once(audio_path)
            elapsed_samples.append(elapsed_ms)
            read_samples.append(float(read_count))
            exists_samples.append(float(exists_count))
            peak_samples.append(peak_bytes)

    payload = {
        "audio_size_bytes": float(AUDIO_SIZE_BYTES),
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "local_uri_exists_calls_mean": statistics.fmean(exists_samples),
        "local_uri_read_bytes_calls_mean": statistics.fmean(read_samples),
        "peak_bytes_mean": statistics.fmean(peak_samples),
        "sample_count": float(SAMPLE_COUNT),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
