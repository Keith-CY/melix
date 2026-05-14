from __future__ import annotations

import base64
import json
import threading
import time
import urllib.request
from pathlib import Path

from tests.integration.helpers import LiveMelixStack, read_metrics_export, wait_for_metric_value

INTERFERENCE_TRANSCRIPTION_DELAY_MS = "1500"


def timed_request(url: str, payload: dict[str, object], *, timeout: float = 15.0) -> tuple[float, bytes, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    started_at = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        content_type = response.headers.get("content-type", "")
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    return elapsed_ms, body, content_type


def parse_json_bytes(body: bytes) -> dict[str, object]:
    return json.loads(body.decode("utf-8"))


def metric_value(snapshot: dict[str, object], key: str) -> float:
    values = snapshot.get("values", {})
    if not isinstance(values, dict):
        return 0.0
    value = values.get(key, 0.0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    stack = LiveMelixStack(
        repo_root,
        environment_overrides={"MELIX_DETERMINISTIC_TRANSCRIPTION_DELAY_MS": INTERFERENCE_TRANSCRIPTION_DELAY_MS},
    )
    stack.start()

    try:
        inline_image = base64.b64encode(b"phase6 vision fixture").decode("ascii")

        ocr_ms, ocr_body, _ = timed_request(
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
        if b"phase6 vision fixture" not in ocr_body:
            raise SystemExit("OCR smoke response did not include the fixture text.")
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        ocr_probe_ms = metric_value(metrics, "vision.ocr_latency_ms")
        ocr_preprocess_ms = metric_value(metrics, "vision.preprocess_latency_ms")
        ocr_peak_memory = metric_value(metrics, "vision.preprocess_peak_memory_bytes")

        vlm_ms, vlm_body, _ = timed_request(
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
        if b"Image content: phase6 vision fixture" not in vlm_body:
            raise SystemExit("VLM smoke response did not include the fixture summary.")
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        vlm_first_token_ms = metric_value(metrics, "vision.vlm_first_token_ms")
        vlm_preprocess_ms = metric_value(metrics, "vision.preprocess_latency_ms")
        vlm_peak_memory = metric_value(metrics, "vision.preprocess_peak_memory_bytes")

        transcription_ms, transcription_body, _ = timed_request(
            f"http://127.0.0.1:{stack.http_port}/v1/audio/transcriptions",
            {
                "model": "melix-dev-transcribe",
                "audio_base64": base64.b64encode(b"phase6 audio smoke").decode("ascii"),
                "format": "wav",
                "language": "en",
            },
        )
        transcription_payload = parse_json_bytes(transcription_body)
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        transcription_probe_ms = metric_value(metrics, "audio.transcription_latency_ms")
        transcription_duration = metric_value(metrics, "audio.audio_duration_seconds")
        transcription_chunks = metric_value(metrics, "audio.audio_chunk_count")
        audio_preprocess_ms = metric_value(metrics, "audio.preprocess_latency_ms")
        audio_peak_memory = metric_value(metrics, "audio.preprocess_peak_memory_bytes")

        speech_ms, speech_body, _ = timed_request(
            f"http://127.0.0.1:{stack.http_port}/v1/audio/speech",
            {
                "model": "melix-dev-speech",
                "input": "phase6 speech smoke",
                "voice": "alloy",
                "format": "wav",
            },
        )
        if speech_body != b"VOICE=alloy\nFORMAT=wav\nTEXT=phase6 speech smoke":
            raise SystemExit("Speech smoke response did not match the deterministic fixture.")
        metrics = read_metrics_export(stack.control_plane_metrics_path)
        speech_probe_ms = metric_value(metrics, "audio.speech_latency_ms")
        speech_output_bytes = metric_value(metrics, "audio.speech_output_bytes")

        interference_result: dict[str, object] = {}

        def run_transcription_load() -> None:
            elapsed_ms, body, _ = timed_request(
                f"http://127.0.0.1:{stack.http_port}/v1/audio/transcriptions",
                {
                    "model": "melix-dev-transcribe",
                    "audio_base64": base64.b64encode(b"phase6 interference load").decode("ascii"),
                    "format": "wav",
                    "language": "en",
                },
            )
            interference_result["transcription_elapsed_ms"] = elapsed_ms
            interference_result["payload"] = parse_json_bytes(body)

        worker = threading.Thread(target=run_transcription_load, daemon=True)
        worker.start()
        wait_for_metric_value(
            stack.control_plane_metrics_path,
            "scheduler.multimodal_active_requests",
            minimum=1,
            timeout_seconds=5.0,
        )
        text_ms, text_body, _ = timed_request(
            stack.chat_url(),
            {
                "model": "melix-dev-text",
                "stream": True,
                "messages": [{"role": "user", "content": "measure text under multimodal load"}],
            },
        )
        worker.join(timeout=10)
        if worker.is_alive():
            raise SystemExit("Interference transcription load did not finish.")
        if b"Echo" not in text_body:
            raise SystemExit("Text-under-load response did not reach the live text path.")

        metrics = read_metrics_export(stack.control_plane_metrics_path)
        text_ttft_under_load = metric_value(metrics, "scheduler.text_ttft_under_multimodal_ms")
        multimodal_queue_delay = metric_value(metrics, "scheduler.multimodal_queue_delay_ms")

        print(
            "ocr "
            f"request_latency_ms={ocr_ms:.2f} "
            f"probe_latency_ms={ocr_probe_ms:.2f} "
            f"preprocess_latency_ms={ocr_preprocess_ms:.2f} "
            f"preprocess_peak_memory_bytes={ocr_peak_memory:.0f}"
        )
        print(
            "vlm "
            f"request_latency_ms={vlm_ms:.2f} "
            f"first_token_latency_ms={vlm_first_token_ms:.2f} "
            f"preprocess_latency_ms={vlm_preprocess_ms:.2f} "
            f"preprocess_peak_memory_bytes={vlm_peak_memory:.0f}"
        )
        print(
            "transcription "
            f"request_latency_ms={transcription_ms:.2f} "
            f"probe_latency_ms={transcription_probe_ms:.2f} "
            f"preprocess_latency_ms={audio_preprocess_ms:.2f} "
            f"preprocess_peak_memory_bytes={audio_peak_memory:.0f} "
            f"duration_seconds={transcription_duration:.6f} "
            f"chunk_count={transcription_chunks:.0f} "
            f"text={transcription_payload['text']}"
        )
        print(
            "speech "
            f"request_latency_ms={speech_ms:.2f} "
            f"probe_latency_ms={speech_probe_ms:.3f} "
            f"output_bytes={speech_output_bytes:.0f}"
        )
        print(
            "text_under_multimodal "
            f"request_latency_ms={text_ms:.2f} "
            f"scheduler_text_ttft_ms={text_ttft_under_load:.2f} "
            f"multimodal_queue_delay_ms={multimodal_queue_delay:.2f}"
        )
    finally:
        stack.stop()


if __name__ == "__main__":
    main()
