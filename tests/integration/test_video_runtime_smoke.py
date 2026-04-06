from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "m16_video_runtime_smoke.py"
MODULE_SPEC = importlib.util.spec_from_file_location("m16_video_runtime_smoke", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
m16_video_runtime_smoke = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(m16_video_runtime_smoke)


def test_video_runtime_smoke_records_live_video_operator_evidence() -> None:
    payload = m16_video_runtime_smoke.run_smoke(Path(__file__).resolve().parents[2])

    assert payload["ok"] is True
    checks = payload["checks"]
    assert checks["video.local_path_success"] is True
    assert checks["video.remote_url_success"] is True
    assert checks["video.bounded_window_success"] is True
    assert checks["video.routing.text_protection_success"] is True

    metrics = payload["metrics"]
    assert metrics["video.integration_success_rate"] == 100.0
    assert metrics["vision.video_frame_count"] == 6.0
    assert metrics["vision.video_frame_budget"] == 6.0
    assert metrics["vision.video_window_ms"] == 4000.0
    assert metrics["vision.temp_media_artifact_count"] >= 1.0
    assert metrics["vision.temp_media_cleanup_failure_count"] == 0.0
    assert metrics["scheduler.text_ttft_under_multimodal_ms"] >= 0.0
    assert metrics["scheduler.multimodal_queue_delay_ms"] >= 0.0

    scenarios = payload["scenarios"]
    assert scenarios["local_path"]["source_reference"].endswith("local-smoke.mp4")
    assert scenarios["remote_url"]["source_reference"].startswith("http://127.0.0.1:")
    assert scenarios["bounded_window"]["source_reference"] == "inline_bytes:bounded-window.mp4"
    assert "Video content: bounded-window.mp4" in scenarios["bounded_window"]["response_excerpt"]
    assert "Echo:" in scenarios["routing"]["text_response_excerpt"]
