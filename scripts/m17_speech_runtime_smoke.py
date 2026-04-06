#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tests.integration.helpers import LiveMelixStack, read_metrics_export
from worker.productization.acceptance_metrics import build_phase17_speech_metrics_report


_AUDIO_RUNTIME_PACK_RECORD = {
    "packID": "melix-audio-runtime-pack",
    "version": "0.3.0",
    "profiles": ["audio-stt", "audio-tts"],
}

_MANAGED_AUDIO_MODELS = {
    "melix-whisper-mlx": {
        "source_model_path": "mlx-community/whisper-large-v3-turbo-asr-fp16",
        "local_relative_path": "models/default-managed/mlx-community/whisper-large-v3-turbo-asr-fp16/mlx-audio",
    },
    "melix-parakeet-mlx": {
        "source_model_path": "mlx-community/parakeet-tdt-0.6b-v2",
        "local_relative_path": "models/default-managed/mlx-community/parakeet-tdt-0.6b-v2/mlx-audio",
    },
    "melix-kokoro-mlx": {
        "source_model_path": "mlx-community/Kokoro-82M-bf16",
        "local_relative_path": "models/default-managed/mlx-community/Kokoro-82M-bf16/mlx-audio",
    },
    "melix-qwen3-tts-mlx": {
        "source_model_path": "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit",
        "local_relative_path": "models/default-managed/mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit/mlx-audio",
    },
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _install_fake_mlx_audio_package(root: Path) -> None:
    (root / "mlx_audio" / "stt").mkdir(parents=True, exist_ok=True)
    (root / "mlx_audio" / "tts").mkdir(parents=True, exist_ok=True)
    for package_path in (
        root / "mlx_audio" / "__init__.py",
        root / "mlx_audio" / "stt" / "__init__.py",
        root / "mlx_audio" / "tts" / "__init__.py",
    ):
        package_path.write_text("", encoding="utf-8")

    (root / "mlx_audio" / "stt" / "utils.py").write_text(
        """
from pathlib import Path
from types import SimpleNamespace


class FakeSTTModel:
    def __init__(self, model_path: str) -> None:
        self.model_path = model_path

    def generate(self, audio_path: str, **kwargs):
        normalized_model_path = self.model_path.lower()
        family = "whisper" if "whisper" in normalized_model_path else "parakeet"
        requested_language = kwargs.get("language") or ""
        detected_language = requested_language if family == "whisper" else ""
        duration_seconds = 1.5 if family == "whisper" else 2.25
        filename = Path(audio_path).name
        return SimpleNamespace(
            text=f"{family} transcription from {filename}",
            language=detected_language,
            total_time=duration_seconds,
        )


def load_model(model_path: str):
    return FakeSTTModel(model_path)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (root / "mlx_audio" / "tts" / "utils.py").write_text(
        """
class FakeChunk:
    def __init__(self, audio, sample_rate=24000):
        self.audio = audio
        self.sample_rate = sample_rate


class FakeKokoroModel:
    voices = ["af_sky", "am_echo"]

    def generate(self, text, voice=None, verbose=False):
        base = [0.10, -0.10, 0.00]
        if voice:
            base.extend([0.05, -0.05])
        yield FakeChunk(base)


class FakeQwen3TTSModel:
    available_voices = ["alloy", "verse"]

    def generate(self, text, voice=None, instruct=None, verbose=False):
        base = [0.00, 0.20, -0.20, 0.10]
        if voice:
            base.extend([0.05, 0.05])
        if instruct:
            base.extend([-0.05, -0.05, 0.02])
        yield FakeChunk(base)


def load_model(model_path: str, strict: bool = True):
    normalized_model_path = model_path.lower()
    if "qwen3" in normalized_model_path:
        return FakeQwen3TTSModel()
    return FakeKokoroModel()
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _install_audio_assets(app_support_dir: Path) -> None:
    runtime_pack_root = app_support_dir / "runtime-packs" / "audio"
    runtime_pack_manifest = runtime_pack_root / "melix-audio-runtime-pack" / "0.3.0" / "runtime-pack.json"
    _write_json(runtime_pack_manifest, _AUDIO_RUNTIME_PACK_RECORD)
    _write_json(
        runtime_pack_root / ".melix-runtime-pack-state.json",
        {
            "audio-stt": _AUDIO_RUNTIME_PACK_RECORD,
            "audio-tts": _AUDIO_RUNTIME_PACK_RECORD,
        },
    )

    managed_model_records: dict[str, dict[str, object]] = {}
    managed_model_root = app_support_dir / "models" / "default-managed"
    for model_id, metadata in _MANAGED_AUDIO_MODELS.items():
        local_model_path = app_support_dir / metadata["local_relative_path"]
        record = {
            "modelID": model_id,
            "revision": "mlx-audio",
            "sourceModelPath": metadata["source_model_path"],
            "localModelPath": str(local_model_path),
        }
        _write_json(local_model_path / "managed-model.json", record)
        managed_model_records[model_id] = record

    _write_json(
        managed_model_root / ".melix-managed-audio-models.json",
        managed_model_records,
    )


def _post_json(
    url: str,
    payload: dict[str, object],
    *,
    timeout: float = 20.0,
) -> tuple[int, object, dict[str, str]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "")
            body = response.read()
            headers = dict(response.headers.items())
            if "application/json" in content_type:
                return response.status, json.loads(body.decode("utf-8")), headers
            return response.status, body, headers
    except urllib.error.HTTPError as exc:
        content_type = exc.headers.get("content-type", "")
        body = exc.read()
        headers = dict(exc.headers.items())
        if "application/json" in content_type:
            return exc.code, json.loads(body.decode("utf-8")), headers
        return exc.code, body, headers


def _timed_post_json(
    url: str,
    payload: dict[str, object],
    *,
    timeout: float = 30.0,
) -> tuple[int, object, dict[str, str], float]:
    deadline = time.time() + timeout
    last_status = 0
    last_body: object = b""
    last_headers: dict[str, str] = {}

    while time.time() < deadline:
        started_at = time.perf_counter()
        status, body, headers = _post_json(url, payload, timeout=min(timeout, 15.0))
        elapsed_ms = (time.perf_counter() - started_at) * 1_000.0
        if status not in {409, 503}:
            return status, body, headers, elapsed_ms
        last_status = status
        last_body = body
        last_headers = headers
        time.sleep(0.25)

    return last_status, last_body, last_headers, timeout * 1_000.0


def _metric_value(snapshot: dict[str, object], key: str) -> float:
    values = snapshot.get("values", {})
    if not isinstance(values, dict):
        return 0.0
    value = values.get(key, 0.0)
    if not isinstance(value, (int, float)):
        return 0.0
    return round(float(value), 2)


def _transcriptions_url(stack: LiveMelixStack) -> str:
    return f"http://127.0.0.1:{stack.http_port}/v1/audio/transcriptions"


def _speech_url(stack: LiveMelixStack) -> str:
    return f"http://127.0.0.1:{stack.http_port}/v1/audio/speech"


def _capture_transcription_scenario(
    stack: LiveMelixStack,
    *,
    model_id: str,
    expected_family: str,
    language: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, object] = {
        "model": model_id,
        "audio_base64": base64.b64encode(b"speech-runtime-smoke").decode("ascii"),
        "format": "wav",
    }
    if language is not None:
        payload["language"] = language

    status, body, _, elapsed_ms = _timed_post_json(_transcriptions_url(stack), payload)
    metrics_snapshot = read_metrics_export(stack.control_plane_metrics_path)
    body_dict = body if isinstance(body, dict) else {}
    response_text = json.dumps(body_dict, sort_keys=True)
    detected_language = str(body_dict.get("language", ""))

    return {
        "model_id": model_id,
        "backend_family": expected_family,
        "success": status == 200 and expected_family in response_text,
        "request_latency_ms": round(elapsed_ms, 2),
        "duration_seconds": float(body_dict.get("duration_seconds", 0.0) or 0.0),
        "detected_language": detected_language,
        "response_excerpt": response_text[:400],
        "preprocess_latency_ms": _metric_value(metrics_snapshot, "audio.preprocess_latency_ms"),
        "preprocess_peak_memory_bytes": _metric_value(
            metrics_snapshot, "audio.preprocess_peak_memory_bytes"
        ),
        "chunk_count": _metric_value(metrics_snapshot, "audio.audio_chunk_count"),
        "transcription_latency_ms": _metric_value(
            metrics_snapshot, "audio.transcription_latency_ms"
        ),
        "language_fallback_count": _metric_value(
            metrics_snapshot, "audio.language_fallback_count"
        ),
    }


def _capture_speech_scenario(
    stack: LiveMelixStack,
    *,
    model_id: str,
    input_text: str,
    voice: str | None = None,
    locale: str | None = None,
    instructions: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, object] = {
        "model": model_id,
        "input": input_text,
        "format": "wav",
    }
    if voice is not None:
        payload["voice"] = voice
    if locale is not None:
        payload["locale"] = locale
    if instructions is not None:
        payload["instructions"] = instructions

    status, body, headers, elapsed_ms = _timed_post_json(_speech_url(stack), payload)
    metrics_snapshot = read_metrics_export(stack.control_plane_metrics_path)
    body_bytes = body if isinstance(body, bytes) else json.dumps(body, sort_keys=True).encode("utf-8")
    requested_locale = headers.get("x-melix-audio-requested-locale", "")
    resolved_locale = headers.get("x-melix-audio-resolved-locale", "")
    locale_source = headers.get("x-melix-audio-locale-source", "")
    locale_policy = headers.get("x-melix-audio-locale-policy", "")
    content_type = headers.get("content-type", "")

    return {
        "model_id": model_id,
        "success": status == 200 and content_type == "audio/wav" and len(body_bytes) > 0,
        "request_latency_ms": round(elapsed_ms, 2),
        "content_type": content_type,
        "output_bytes": len(body_bytes),
        "requested_locale": requested_locale,
        "resolved_locale": resolved_locale,
        "locale_source": locale_source,
        "locale_policy": locale_policy,
        "model_default_locale": headers.get("x-melix-audio-model-default-locale", ""),
        "packaged_default_locale": headers.get("x-melix-audio-packaged-default-locale", ""),
        "supported_locales": headers.get("x-melix-audio-supported-locales", ""),
        "locale_resolution_success": bool(
            not locale
            or (
                requested_locale == locale.replace("_", "-").lower()
                and resolved_locale != ""
                and locale_source == "request"
            )
        ),
        "instruction_path_success": bool(
            instructions is None or _metric_value(metrics_snapshot, "audio.voice_fallback_count") == 0.0
        ),
        "speech_latency_ms": _metric_value(metrics_snapshot, "audio.speech_latency_ms"),
        "voice_fallback_count": _metric_value(metrics_snapshot, "audio.voice_fallback_count"),
        "response_excerpt": body_bytes[:24].hex(),
    }


def run_smoke(repo_root: Path) -> dict[str, Any]:
    scratch_root = Path(tempfile.mkdtemp(prefix="melix-m17-speech-smoke-"))
    app_support_dir = scratch_root / "app-support"
    fake_python_root = scratch_root / "fake-python"
    _install_fake_mlx_audio_package(fake_python_root)
    _install_audio_assets(app_support_dir)

    stack = LiveMelixStack(
        repo_root,
        environment_overrides={
            "MELIX_APP_SUPPORT_DIR": str(app_support_dir),
            "MELIX_PYTHONPATH_PREFIX": str(fake_python_root),
        },
    )

    try:
        stack.start()

        whisper = _capture_transcription_scenario(
            stack,
            model_id="melix-whisper-mlx",
            expected_family="whisper",
        )
        parakeet = _capture_transcription_scenario(
            stack,
            model_id="melix-parakeet-mlx",
            expected_family="parakeet",
            language="en",
        )
        kokoro = _capture_speech_scenario(
            stack,
            model_id="melix-kokoro-mlx",
            input_text="Hello from Kokoro.",
            voice="af_sky",
            locale="en-US",
        )
        qwen3_tts = _capture_speech_scenario(
            stack,
            model_id="melix-qwen3-tts-mlx",
            input_text="Switch to English and speak calmly.",
            voice="alloy",
            locale="en-US",
            instructions="Speak calmly.",
        )

        report = build_phase17_speech_metrics_report(
            whisper=whisper,
            parakeet=parakeet,
            kokoro=kokoro,
            qwen3_tts=qwen3_tts,
        )
        return {
            "ok": all(report["checks"].values()),
            "checks": report["checks"],
            "metrics": report["metrics"],
            "scenarios": {
                "whisper": whisper,
                "parakeet": parakeet,
                "kokoro": kokoro,
                "qwen3_tts": qwen3_tts,
            },
        }
    finally:
        stack.stop()
        shutil.rmtree(scratch_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = run_smoke(args.repo_root.resolve())
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
