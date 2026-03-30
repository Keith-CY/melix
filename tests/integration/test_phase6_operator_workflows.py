from __future__ import annotations

import base64
import json
from pathlib import Path
import threading
import time
import urllib.request

from tests.integration.helpers import LiveMelixStack, read_metrics_export


def _post_json(url: str, payload: dict[str, object], *, timeout: float = 10.0) -> tuple[int, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        body = response.read()
        if "application/json" in content_type:
            return response.status, json.loads(body.decode("utf-8"))
        return response.status, body


def test_text_requests_record_interference_metrics_during_multimodal_load() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        environment_overrides={"MELIX_DETERMINISTIC_TRANSCRIPTION_DELAY_MS": "150"},
    )

    transcription_response: dict[str, object] = {}

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-transcribe"])
        def run_transcription() -> None:
            status, payload = _post_json(
                f"http://127.0.0.1:{stack.http_port}/v1/audio/transcriptions",
                {
                    "model": "melix-dev-transcribe",
                    "audio_base64": base64.b64encode(b"phase6 interference load").decode("ascii"),
                    "format": "wav",
                    "language": "en",
                },
            )
            transcription_response["status"] = status
            transcription_response["payload"] = payload

        worker = threading.Thread(target=run_transcription, daemon=True)
        worker.start()
        time.sleep(0.05)

        chat_status, chat_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "measure text under multimodal load"}],
            },
        )
        worker.join(timeout=5)

        assert not worker.is_alive()
        assert chat_status == 200
        assert b"Echo" in chat_payload
        assert b"data: [DONE]" in chat_payload
        assert transcription_response["status"] == 200

        metrics = read_metrics_export(stack.control_plane_metrics_path)
        values = metrics["values"]
        assert values["scheduler.text_ttft_under_multimodal_ms"] >= 0
        assert values["audio.transcription_latency_ms"] >= 0
    finally:
        stack.stop()


def test_multimodal_operator_smoke_records_phase6_metrics() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])

    try:
        stack.start()
        stack.wait_for_models(
            [
                "melix-dev-ocr",
                "melix-dev-vlm",
                "melix-dev-transcribe",
                "melix-dev-speech",
            ]
        )
        inline_image = base64.b64encode(b"phase6 vision fixture").decode("ascii")

        ocr_status, ocr_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-ocr",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract the image text."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "data": inline_image,
                                    "mime_type": "image/png",
                                    "format": "png",
                                    "filename": "ocr-fixture.png",
                                },
                            },
                        ],
                    }
                ],
            },
        )
        assert ocr_status == 200
        assert b"phase6 vision fixture" in ocr_payload

        vlm_status, vlm_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Summarize the image."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "data": inline_image,
                                    "mime_type": "image/png",
                                    "format": "png",
                                    "filename": "vlm-fixture.png",
                                },
                            },
                        ],
                    }
                ],
            },
        )
        assert vlm_status == 200
        assert b"Image content: phase6 vision fixture" in vlm_payload
        assert b"Prompt: Summarize the image." in vlm_payload

        repeated_vlm_status, repeated_vlm_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Summarize the image."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "data": inline_image,
                                    "mime_type": "image/png",
                                    "format": "png",
                                    "filename": "vlm-fixture.png",
                                },
                            },
                        ],
                    }
                ],
            },
        )
        assert repeated_vlm_status == 200
        assert b"Image content: phase6 vision fixture" in repeated_vlm_payload

        transcription_status, transcription_payload = _post_json(
            f"http://127.0.0.1:{stack.http_port}/v1/audio/transcriptions",
            {
                "model": "melix-dev-transcribe",
                "audio_base64": base64.b64encode(b"phase6 audio smoke").decode("ascii"),
                "format": "wav",
                "language": "en",
            },
        )
        assert transcription_status == 200
        assert transcription_payload["text"] == "phase6 audio smoke"

        speech_status, speech_payload = _post_json(
            f"http://127.0.0.1:{stack.http_port}/v1/audio/speech",
            {
                "model": "melix-dev-speech",
                "input": "phase6 speech smoke",
                "voice": "alloy",
                "format": "wav",
            },
        )
        assert speech_status == 200
        assert speech_payload == b"VOICE=alloy\nFORMAT=wav\nTEXT=phase6 speech smoke"

        metrics = read_metrics_export(stack.control_plane_metrics_path)
        values = metrics["values"]
        assert values["vision.ocr_latency_ms"] >= 0
        assert values["vision.vlm_first_token_ms"] >= 0
        assert values["vision.preprocess_peak_memory_bytes"] > 0
        assert values["vision.cache_memory_bytes"] > 0
        assert values["vision.cache_hit_rate"] > 0
        assert values["cache.memory_bytes"] > 0
        assert values["cache.hit_rate"] > 0
        assert values["audio.transcription_latency_ms"] >= 0
        assert values["audio.speech_latency_ms"] >= 0
        assert values["audio.speech_output_bytes"] > 0
    finally:
        stack.stop()
