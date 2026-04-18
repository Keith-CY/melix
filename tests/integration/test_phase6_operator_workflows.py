from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.request

from tests.integration.helpers import LiveMelixStack, read_metrics_export, wait_for_metric_value
from worker.productization.acceptance_metrics import build_phase6_vision_metrics_report

INTERFERENCE_TRANSCRIPTION_DELAY_MS = "500"


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


def _timed_post_json(
    url: str,
    payload: dict[str, object],
    *,
    timeout: float = 10.0,
) -> tuple[int, object, float]:
    started_at = time.perf_counter()
    status, body = _post_json(url, payload, timeout=timeout)
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    return status, body, elapsed_ms


def _start_image_fixture_server(payload: bytes, *, content_type: str = "image/png") -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}/fixture.png"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, url


def test_text_requests_record_interference_metrics_during_multimodal_load() -> None:
    stack = LiveMelixStack(
        Path(__file__).resolve().parents[2],
        environment_overrides={"MELIX_DETERMINISTIC_TRANSCRIPTION_DELAY_MS": INTERFERENCE_TRANSCRIPTION_DELAY_MS},
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
        wait_for_metric_value(
            stack.control_plane_metrics_path,
            "scheduler.multimodal_active_requests",
            minimum=1,
            timeout_seconds=5.0,
        )

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


def test_ocr_chat_applies_default_and_overridden_stop_sequences() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    inline_image = base64.b64encode(b"title<ocr:end>body").decode("ascii")

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-ocr"])

        default_status, default_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-ocr",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "input_image": {
                                    "data": inline_image,
                                    "mime_type": "image/png",
                                    "format": "png",
                                    "filename": "ocr-default-stop.png",
                                },
                            }
                        ],
                    }
                ],
            },
        )
        override_status, override_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-ocr",
                "stream": True,
                "stop": ["body"],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "input_image": {
                                    "data": inline_image,
                                    "mime_type": "image/png",
                                    "format": "png",
                                    "filename": "ocr-request-stop.png",
                                },
                            }
                        ],
                    }
                ],
            },
        )

        assert default_status == 200
        assert override_status == 200
        assert b"title" in default_payload
        assert b"<ocr:end>" not in default_payload
        assert b"body" not in default_payload
        assert b"title<ocr:end>" in override_payload
        assert b"body" not in override_payload
    finally:
        stack.stop()


def test_multimodal_chat_accepts_local_and_remote_image_urls(tmp_path: Path) -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    local_image = tmp_path / "local-image.txt"
    local_image.write_text("phase6 local image fixture")
    remote_server, remote_url = _start_image_fixture_server(b"phase6 remote image fixture")

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-vlm"])

        local_status, local_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Summarize the local image."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(local_image),
                                    "mime_type": "image/png",
                                    "filename": local_image.name,
                                },
                            },
                        ],
                    }
                ],
            },
        )
        assert local_status == 200
        assert b"Image content: phase6 local image fixture" in local_payload
        assert b"Prompt: Summarize the local image." in local_payload

        remote_status, remote_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Summarize the remote image."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": remote_url,
                                    "mime_type": "image/png",
                                    "filename": "fixture.png",
                                },
                            },
                        ],
                    }
                ],
            },
        )
        assert remote_status == 200
        assert b"Image content: phase6 remote image fixture" in remote_payload
        assert b"Prompt: Summarize the remote image." in remote_payload
    finally:
        remote_server.shutdown()
        remote_server.server_close()
        stack.stop()


def test_multimodal_chat_preserves_multi_image_order(tmp_path: Path) -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    first_image = tmp_path / "first-image.txt"
    second_image = tmp_path / "second-image.txt"
    first_image.write_text("phase6 first image")
    second_image.write_text("phase6 second image")

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-vlm"])

        status, payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Compare the images."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(first_image),
                                    "mime_type": "image/png",
                                    "filename": first_image.name,
                                },
                            },
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(second_image),
                                    "mime_type": "image/png",
                                    "filename": second_image.name,
                                },
                            },
                        ],
                    }
                ],
            },
        )

        assert status == 200
        assert b"Image 1 content: phase6 first image" in payload
        assert b"Image 2 content: phase6 second image" in payload
        assert b"Prompt: Compare the images." in payload
    finally:
        stack.stop()


def test_multimodal_chat_accepts_image_only_requests() -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    inline_image = base64.b64encode(b"phase6 image only").decode("ascii")

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-ocr", "melix-dev-vlm"])

        ocr_status, ocr_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-ocr",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "input_image": {
                                    "data": inline_image,
                                    "mime_type": "image/png",
                                    "filename": "ocr-image-only.png",
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert ocr_status == 200
        assert b"phase6 image only" in ocr_payload

        vlm_status, vlm_payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "input_image": {
                                    "data": inline_image,
                                    "mime_type": "image/png",
                                    "filename": "vlm-image-only.png",
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert vlm_status == 200
        assert b"Image content: phase6 image only" in vlm_payload
        assert b"Prompt: Describe the image." in vlm_payload
    finally:
        stack.stop()


def test_multimodal_chat_streams_tool_calls_with_shared_parser_selection(tmp_path: Path) -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    image_path = tmp_path / "tool-image.txt"
    image_path.write_text("phase6 tool image")

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-vlm"])

        status, payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "tool_parser": {
                    "mode": "qwen",
                    "namespaces": ["tools.vision"],
                    "xml_fallback": True,
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Call the tool for this image."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(image_path),
                                    "mime_type": "image/png",
                                    "filename": image_path.name,
                                },
                            },
                        ],
                    }
                ],
            },
        )

        assert status == 200
        assert b"event: tool_call" in payload
        assert b"\"parser_mode\":\"qwen\"" in payload
        assert b"\"parser_namespaces\":[\"tools.vision\"]" in payload
        assert b"\"parser_fallback_mode\":\"xml\"" in payload
        assert b"\"name\":\"tools.vision\"" in payload
        assert b"Image content: phase6 tool image" in payload
        assert b"Prompt: Call the tool for this image." in payload
    finally:
        stack.stop()


def test_multimodal_chat_uses_model_default_parser_selection_for_llava_family(tmp_path: Path) -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    image_path = tmp_path / "default-tool-image.txt"
    image_path.write_text("phase6 default tool image")

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-vlm"])

        status, payload = _post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Call the tool for this image."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(image_path),
                                    "mime_type": "image/png",
                                    "filename": image_path.name,
                                },
                            },
                        ],
                    }
                ],
            },
        )

        assert status == 200
        assert b"event: tool_call" in payload
        assert b"\"parser_mode\":\"qwen\"" in payload
        assert b"\"parser_namespaces\":[\"tools.vision\"]" in payload
        assert b"\"parser_fallback_mode\":\"xml\"" in payload
        assert b"\"name\":\"tools.vision\"" in payload
    finally:
        stack.stop()


def test_phase6_vision_evidence_report_is_machine_readable(tmp_path: Path) -> None:
    stack = LiveMelixStack(Path(__file__).resolve().parents[2])
    local_image = tmp_path / "vision-local.txt"
    local_image.write_text("phase6 local evidence image")
    multi_first = tmp_path / "vision-multi-1.txt"
    multi_second = tmp_path / "vision-multi-2.txt"
    multi_first.write_text("phase6 multi first")
    multi_second.write_text("phase6 multi second")
    tool_image = tmp_path / "vision-tool.txt"
    tool_image.write_text("phase6 tool evidence image")
    remote_server, remote_url = _start_image_fixture_server(b"phase6 remote evidence image")
    ocr_image = base64.b64encode(b"title<ocr:end>body").decode("ascii")

    try:
        stack.start()
        stack.wait_for_models(["melix-dev-ocr", "melix-dev-vlm"])

        local_status, local_payload, _ = _timed_post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Summarize the local evidence image."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(local_image),
                                    "mime_type": "image/png",
                                    "filename": local_image.name,
                                },
                            },
                        ],
                    }
                ],
            },
        )

        remote_status, remote_payload, _ = _timed_post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Summarize the remote evidence image."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": remote_url,
                                    "mime_type": "image/png",
                                    "filename": "remote-evidence.png",
                                },
                            },
                        ],
                    }
                ],
            },
        )

        multi_status, multi_payload, _ = _timed_post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Compare the evidence images."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(multi_first),
                                    "mime_type": "image/png",
                                    "filename": multi_first.name,
                                },
                            },
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(multi_second),
                                    "mime_type": "image/png",
                                    "filename": multi_second.name,
                                },
                            },
                        ],
                    }
                ],
            },
        )

        ocr_status, ocr_payload, ocr_elapsed_ms = _timed_post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-ocr",
                "stream": True,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "input_image": {
                                    "data": ocr_image,
                                    "mime_type": "image/png",
                                    "format": "png",
                                    "filename": "ocr-evidence.png",
                                },
                            }
                        ],
                    }
                ],
            },
        )

        tool_status, tool_payload, tool_elapsed_ms = _timed_post_json(
            stack.chat_url(),
            {
                "model": "melix-dev-vlm",
                "stream": True,
                "tool_parser": {
                    "mode": "qwen",
                    "namespaces": ["tools.vision"],
                    "xml_fallback": True,
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Call the tool for this image."},
                            {
                                "type": "input_image",
                                "input_image": {
                                    "url": str(tool_image),
                                    "mime_type": "image/png",
                                    "filename": tool_image.name,
                                },
                            },
                        ],
                    }
                ],
            },
        )

        report = build_phase6_vision_metrics_report(
            ingress={
                "local_image_success": (
                    local_status == 200
                    and b"Image content: phase6 local evidence image" in local_payload
                ),
                "remote_image_success": (
                    remote_status == 200
                    and b"Image content: phase6 remote evidence image" in remote_payload
                ),
                "multi_image_success": (
                    multi_status == 200
                    and b"Image 1 content: phase6 multi first" in multi_payload
                    and b"Image 2 content: phase6 multi second" in multi_payload
                ),
            },
            ocr={
                "request_latency_ms": ocr_elapsed_ms,
                "default_stop_success": (
                    ocr_status == 200
                    and b"title" in ocr_payload
                    and b"<ocr:end>" not in ocr_payload
                    and b"body" not in ocr_payload
                ),
            },
            vlm={
                "request_latency_ms": tool_elapsed_ms,
                "tool_call_success": (
                    tool_status == 200
                    and b"event: tool_call" in tool_payload
                    and b"\"name\":\"tools.vision\"" in tool_payload
                ),
            },
            metrics_snapshot=read_metrics_export(stack.control_plane_metrics_path),
        )

        metrics = report["metrics"]
        checks = report["checks"]
        assert checks["vision.ingress.local_image_success"] is True
        assert checks["vision.ingress.remote_image_success"] is True
        assert checks["vision.ingress.multi_image_success"] is True
        assert checks["vision.ocr.default_stop_success"] is True
        assert checks["vision.vlm.tool_call_success"] is True
        assert metrics["vision.integration_success_rate"] == 100.0
        assert metrics["vision.ingress.local_image_success_rate"] == 100.0
        assert metrics["vision.ingress.remote_image_success_rate"] == 100.0
        assert metrics["vision.ingress.multi_image_success_rate"] == 100.0
        assert metrics["vision.ocr.default_stop_success_rate"] == 100.0
        assert metrics["vision.vlm.tool_call_success_rate"] == 100.0
        assert metrics["vision.ocr.request_latency_ms"] >= 0
        assert metrics["vision.vlm.request_latency_ms"] >= 0
        assert metrics["vision.ocr_latency_ms"] >= 0
        assert metrics["vision.vlm_first_token_ms"] >= 0
        assert metrics["vision.preprocess_peak_memory_bytes"] > 0
        assert metrics["vision.cache_memory_bytes"] > 0
    finally:
        remote_server.shutdown()
        remote_server.server_close()
        stack.stop()
