from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.model_ops.errors import ModelOperationError


@dataclass(frozen=True)
class DownloadSnapshot:
    stage: str
    pct: float
    manifest_json: str


@dataclass(frozen=True)
class DownloadPipelineResult:
    output_path: Path
    snapshots: list[DownloadSnapshot]


@dataclass(frozen=True)
class _RetryableDownloadFailure(Exception):
    manifest_json: str


@dataclass(frozen=True)
class _StalledDownloadFailure(Exception):
    manifest_json: str


class DownloadPipeline:
    def run(
        self,
        request: maintenance_pb2.ConvertModelRequest,
        *,
        job_id: str,
        output_dir: Path,
    ) -> DownloadPipelineResult:
        ext = dict(request.ext)
        output_path = output_dir / "download.artifact"
        partial_path = output_dir / "download.artifact.partial"
        state_path = output_dir / "download.state.json"
        source_path = self._resolve_source_path(
            request=request,
            output_dir=output_dir,
            ext=ext,
        )

        selected_mirror = self._selected_mirror(ext)
        total_bytes = source_path.stat().st_size
        chunk_bytes = max(1, self._int(ext.get("chunk_bytes"), default=256))
        max_retries = max(0, self._int(ext.get("max_retries"), default=1))
        fail_after_bytes = max(0, self._int(ext.get("test_fail_after_bytes"), default=0))
        remaining_failures = max(0, self._int(ext.get("test_failures_before_success"), default=0))
        stall_after_bytes = max(0, self._int(ext.get("test_stall_after_bytes"), default=0))
        stall_elapsed_ms = max(0, self._int(ext.get("test_stall_elapsed_ms"), default=0))
        stall_timeout_ms = max(1, self._int(ext.get("stall_timeout_ms"), default=30_000))

        retry_count = 0
        stall_detection_count = 0
        resume_from_bytes = self._resume_from_bytes(partial_path=partial_path, total_bytes=total_bytes)
        resume_used = resume_from_bytes > 0
        snapshots: list[DownloadSnapshot] = [
            self._snapshot(
                request=request,
                job_id=job_id,
                output_dir=output_dir,
                output_path=output_path,
                partial_path=partial_path,
                state_path=state_path,
                selected_mirror=selected_mirror,
                status="running",
                terminal_state="running",
                stage="prepare",
                pct=0.0 if total_bytes == 0 else resume_from_bytes / total_bytes,
                downloaded_bytes=resume_from_bytes,
                total_bytes=total_bytes,
                retry_count=retry_count,
                resume_used=resume_used,
                resume_from_bytes=resume_from_bytes,
                stall_detection_count=stall_detection_count,
                stall_reason="",
            )
        ]

        while True:
            try:
                downloaded_bytes = self._resume_from_bytes(
                    partial_path=partial_path,
                    total_bytes=total_bytes,
                )
                with source_path.open("rb") as source_file:
                    source_file.seek(downloaded_bytes)
                    with partial_path.open("ab") as partial_file:
                        while True:
                            chunk = source_file.read(chunk_bytes)
                            if not chunk:
                                break

                            partial_file.write(chunk)
                            partial_file.flush()
                            downloaded_bytes += len(chunk)
                            snapshots.append(
                                self._snapshot(
                                    request=request,
                                    job_id=job_id,
                                    output_dir=output_dir,
                                    output_path=output_path,
                                    partial_path=partial_path,
                                    state_path=state_path,
                                    selected_mirror=selected_mirror,
                                    status="running",
                                    terminal_state="running",
                                    stage="download",
                                    pct=0.0 if total_bytes == 0 else downloaded_bytes / total_bytes,
                                    downloaded_bytes=downloaded_bytes,
                                    total_bytes=total_bytes,
                                    retry_count=retry_count,
                                    resume_used=resume_used,
                                    resume_from_bytes=resume_from_bytes,
                                    stall_detection_count=stall_detection_count,
                                    stall_reason="",
                                )
                            )

                            if stall_after_bytes and downloaded_bytes >= stall_after_bytes and stall_elapsed_ms > stall_timeout_ms:
                                stall_detection_count += 1
                                raise _StalledDownloadFailure(
                                    manifest_json=self._build_manifest_json(
                                        request=request,
                                        job_id=job_id,
                                        output_dir=output_dir,
                                        output_path=output_path,
                                        partial_path=partial_path,
                                        state_path=state_path,
                                        selected_mirror=selected_mirror,
                                        status="stalled",
                                        terminal_state="stalled",
                                        stage="download",
                                        pct=0.0 if total_bytes == 0 else downloaded_bytes / total_bytes,
                                        downloaded_bytes=downloaded_bytes,
                                        total_bytes=total_bytes,
                                        retry_count=retry_count,
                                        resume_used=resume_used,
                                        resume_from_bytes=resume_from_bytes,
                                        stall_detection_count=stall_detection_count,
                                        stall_reason="no_progress_timeout",
                                    )
                                )

                            if remaining_failures > 0 and fail_after_bytes and downloaded_bytes >= fail_after_bytes:
                                remaining_failures -= 1
                                raise _RetryableDownloadFailure(
                                    manifest_json=self._build_manifest_json(
                                        request=request,
                                        job_id=job_id,
                                        output_dir=output_dir,
                                        output_path=output_path,
                                        partial_path=partial_path,
                                        state_path=state_path,
                                        selected_mirror=selected_mirror,
                                        status="retrying",
                                        terminal_state="running",
                                        stage="download",
                                        pct=0.0 if total_bytes == 0 else downloaded_bytes / total_bytes,
                                        downloaded_bytes=downloaded_bytes,
                                        total_bytes=total_bytes,
                                        retry_count=retry_count,
                                        resume_used=resume_used,
                                        resume_from_bytes=resume_from_bytes,
                                        stall_detection_count=stall_detection_count,
                                        stall_reason="",
                                    )
                                )

                os.replace(os.fspath(partial_path), os.fspath(output_path))
                snapshots.append(
                    self._snapshot(
                        request=request,
                        job_id=job_id,
                        output_dir=output_dir,
                        output_path=output_path,
                        partial_path=partial_path,
                        state_path=state_path,
                        selected_mirror=selected_mirror,
                        status="completed",
                        terminal_state="completed",
                        stage="download",
                        pct=1.0,
                        downloaded_bytes=total_bytes,
                        total_bytes=total_bytes,
                        retry_count=retry_count,
                        resume_used=resume_used,
                        resume_from_bytes=resume_from_bytes,
                        stall_detection_count=stall_detection_count,
                        stall_reason="",
                    )
                )
                return DownloadPipelineResult(output_path=output_path, snapshots=snapshots)
            except _RetryableDownloadFailure as exc:
                if retry_count >= max_retries:
                    terminal_json = self._terminal_manifest_json(
                        exc.manifest_json,
                        status="failed",
                        state_path=state_path,
                    )
                    raise ModelOperationError(
                        code="download_retry_exhausted",
                        message="Download failed after exhausting retries.",
                        details={"state_json": terminal_json},
                    ) from exc
                retry_count += 1
            except _StalledDownloadFailure as exc:
                if retry_count >= max_retries:
                    terminal_json = self._terminal_manifest_json(
                        exc.manifest_json,
                        status="stalled",
                        state_path=state_path,
                    )
                    raise ModelOperationError(
                        code="download_stalled",
                        message="Download stalled without progress.",
                        details={"state_json": terminal_json},
                    ) from exc
                retry_count += 1

    @staticmethod
    def _resume_from_bytes(*, partial_path: Path, total_bytes: int) -> int:
        if not partial_path.exists():
            return 0
        return min(partial_path.stat().st_size, total_bytes)

    @staticmethod
    def _selected_mirror(ext: dict[str, str]) -> str:
        explicit = ext.get("mirror_url", "").strip()
        if explicit:
            return explicit
        mirrors = [part.strip() for part in ext.get("mirror_urls", "").split(",") if part.strip()]
        if mirrors:
            return mirrors[0]
        return "https://huggingface.co"

    @staticmethod
    def _resolve_source_path(
        *,
        request: maintenance_pb2.ConvertModelRequest,
        output_dir: Path,
        ext: dict[str, str],
    ) -> Path:
        source_path_raw = ext.get("source_path", "").strip()
        if source_path_raw:
            source_path = Path(source_path_raw).expanduser().resolve()
            if not source_path.is_file():
                raise ModelOperationError(
                    code="invalid_argument",
                    message="download requires a valid ext.source_path file.",
                )
            return source_path

        synthetic_source = output_dir / ".download-source.bin"
        payload = json.dumps(
            {
                "source_model": request.source_model,
                "operation": "download",
                "ext": ext,
            },
            sort_keys=True,
        ).encode("utf-8")
        synthetic_source.write_bytes(payload)
        return synthetic_source

    @staticmethod
    def _int(raw_value: str | None, *, default: int) -> int:
        if raw_value is None or raw_value == "":
            return default
        try:
            return int(raw_value)
        except ValueError:
            return default

    def _snapshot(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        output_dir: Path,
        output_path: Path,
        partial_path: Path,
        state_path: Path,
        selected_mirror: str,
        status: str,
        terminal_state: str,
        stage: str,
        pct: float,
        downloaded_bytes: int,
        total_bytes: int,
        retry_count: int,
        resume_used: bool,
        resume_from_bytes: int,
        stall_detection_count: int,
        stall_reason: str,
    ) -> DownloadSnapshot:
        manifest_json = self._build_manifest_json(
            request=request,
            job_id=job_id,
            output_dir=output_dir,
            output_path=output_path,
            partial_path=partial_path,
            state_path=state_path,
            selected_mirror=selected_mirror,
            status=status,
            terminal_state=terminal_state,
            stage=stage,
            pct=pct,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
            retry_count=retry_count,
            resume_used=resume_used,
            resume_from_bytes=resume_from_bytes,
            stall_detection_count=stall_detection_count,
            stall_reason=stall_reason,
        )
        return DownloadSnapshot(stage=stage, pct=pct, manifest_json=manifest_json)

    def _build_manifest_json(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        output_dir: Path,
        output_path: Path,
        partial_path: Path,
        state_path: Path,
        selected_mirror: str,
        status: str,
        terminal_state: str,
        stage: str,
        pct: float,
        downloaded_bytes: int,
        total_bytes: int,
        retry_count: int,
        resume_used: bool,
        resume_from_bytes: int,
        stall_detection_count: int,
        stall_reason: str,
    ) -> str:
        payload = {
            "schema_version": "melix.download_job.v1",
            "job_id": job_id,
            "operation": "download",
            "source_model": request.source_model,
            "output_dir": str(output_dir),
            "status": status,
            "terminal_state": terminal_state,
            "stage": stage,
            "pct": round(pct, 6),
            "source_path": request.ext.get("source_path", ""),
            "output_path": str(output_path),
            "partial_path": str(partial_path),
            "state_path": str(state_path),
            "selected_mirror": selected_mirror,
            "downloaded_bytes": downloaded_bytes,
            "total_bytes": total_bytes,
            "resume_used": resume_used,
            "resume_from_bytes": resume_from_bytes,
            "retry_count": retry_count,
            "stall_detection_count": stall_detection_count,
            "stall_reason": stall_reason,
            "ext": dict(request.ext),
            "metrics": {
                "download.resume_success_rate": 1.0 if resume_used and terminal_state == "completed" else 0.0,
                "download.retry_count": retry_count,
                "download.stall_detection_count": stall_detection_count,
            },
        }
        self._write_json_atomically(state_path, payload)
        return json.dumps(payload, sort_keys=True)

    @staticmethod
    def _terminal_manifest_json(manifest_json: str, *, status: str, state_path: Path) -> str:
        payload = json.loads(manifest_json)
        payload["status"] = status
        if status == "failed":
            payload["terminal_state"] = "failed"
        elif status == "stalled":
            payload["terminal_state"] = "stalled"
        DownloadPipeline._write_json_atomically(state_path, payload)
        return json.dumps(payload, sort_keys=True)

    @staticmethod
    def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temp_path = Path(temp_file.name)
        try:
            with temp_file:
                json.dump(payload, temp_file, sort_keys=True)
            os.replace(os.fspath(temp_path), os.fspath(path))
        finally:
            temp_path.unlink(missing_ok=True)
