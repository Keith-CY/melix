from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter
from typing import Callable
import shutil


@dataclass(frozen=True)
class TempMediaCleanupReport:
    session_root: str
    artifact_count: int
    artifact_bytes: int
    cleanup_latency_ms: float
    cleanup_failure_count: int
    cleanup_error_message: str = ""


class TempMediaSession:
    def __init__(
        self,
        *,
        temp_root: Path | str | None = None,
        prefix: str = "melix-media-",
        cleanup_impl: Callable[[Path], None] | None = None,
    ) -> None:
        self._temp_root = Path(temp_root) if temp_root is not None else None
        self._prefix = prefix
        self._cleanup_impl = cleanup_impl or shutil.rmtree
        self._session_root: Path | None = None
        self._artifact_count = 0
        self._artifact_bytes = 0
        self._cleanup_report = TempMediaCleanupReport(
            session_root="",
            artifact_count=0,
            artifact_bytes=0,
            cleanup_latency_ms=0.0,
            cleanup_failure_count=0,
            cleanup_error_message="",
        )
        self._cleanup_finished = False

    @property
    def session_root(self) -> Path | None:
        return self._session_root

    def write_bytes(self, relative_name: str, payload: bytes) -> Path:
        root = self._ensure_session_root()
        artifact_path = root / relative_name
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(payload)
        self._artifact_count += 1
        self._artifact_bytes += len(payload)
        return artifact_path

    def cleanup(self) -> TempMediaCleanupReport:
        if self._cleanup_finished:
            return self._cleanup_report
        self._cleanup_finished = True
        if self._session_root is None:
            return self._cleanup_report

        started_at = perf_counter()
        failure_count = 0
        error_message = ""
        try:
            self._cleanup_impl(self._session_root)
        except OSError as exc:
            failure_count = 1
            error_message = str(exc)
        self._cleanup_report = TempMediaCleanupReport(
            session_root=str(self._session_root),
            artifact_count=self._artifact_count,
            artifact_bytes=self._artifact_bytes,
            cleanup_latency_ms=max(0.0, (perf_counter() - started_at) * 1000.0),
            cleanup_failure_count=failure_count,
            cleanup_error_message=error_message,
        )
        return self._cleanup_report

    def _ensure_session_root(self) -> Path:
        if self._session_root is None:
            if self._temp_root is not None:
                self._temp_root.mkdir(parents=True, exist_ok=True)
            self._session_root = Path(
                mkdtemp(
                    prefix=self._prefix,
                    dir=str(self._temp_root) if self._temp_root is not None else None,
                )
            )
        return self._session_root
