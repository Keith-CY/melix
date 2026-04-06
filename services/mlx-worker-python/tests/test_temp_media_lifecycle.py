from __future__ import annotations

from pathlib import Path

from worker.runtime.temp_media_lifecycle import TempMediaSession


def test_temp_media_session_tracks_artifacts_and_cleans_up_idempotently(tmp_path: Path) -> None:
    session = TempMediaSession(temp_root=tmp_path)

    first_path = session.write_bytes("frames/frame-0.png", b"frame-0")
    second_path = session.write_bytes("videos/clip.mp4", b"clip-data")
    session_root = session.session_root

    assert session_root is not None
    assert first_path.exists()
    assert second_path.exists()

    report = session.cleanup()

    assert report.session_root == str(session_root)
    assert report.artifact_count == 2
    assert report.artifact_bytes == len(b"frame-0") + len(b"clip-data")
    assert report.cleanup_latency_ms >= 0.0
    assert report.cleanup_failure_count == 0
    assert not session_root.exists()
    assert session.cleanup() == report


def test_temp_media_session_reports_cleanup_failures(tmp_path: Path) -> None:
    def failing_cleanup(_path: Path) -> None:
        raise OSError("cleanup failed")

    session = TempMediaSession(
        temp_root=tmp_path,
        cleanup_impl=failing_cleanup,
    )
    artifact_path = session.write_bytes("frames/frame-0.png", b"frame-0")

    report = session.cleanup()

    assert artifact_path.exists()
    assert report.artifact_count == 1
    assert report.artifact_bytes == len(b"frame-0")
    assert report.cleanup_failure_count == 1
    assert report.cleanup_error_message == "cleanup failed"
