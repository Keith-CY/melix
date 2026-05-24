from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_registry.dflash_metadata import dflash_draft_metadata

_HF_AUTH_FAILED_MESSAGE = "Hugging Face authentication failed. Check your token and try again."
_HF_TOKEN_EXT_KEYS = {
    "melix.hf_token",
    "hf_token",
    "HUGGINGFACE_HUB_TOKEN",
    "HF_TOKEN",
}


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
class _DownloadManifestContext:
    state_path: Path
    base_payload: dict[str, Any]
    pending_artifact_integrity: dict[str, Any] | None
    passed_artifact_integrity: dict[str, Any] | None


@dataclass(frozen=True)
class _RetryableDownloadFailure(Exception):
    manifest_payload: dict[str, Any]


@dataclass(frozen=True)
class _StalledDownloadFailure(Exception):
    manifest_payload: dict[str, Any]


class DownloadPipeline:
    def run(
        self,
        request: maintenance_pb2.ConvertModelRequest,
        *,
        job_id: str,
        output_dir: Path,
    ) -> DownloadPipelineResult:
        ext = dict(request.ext)
        strict_integrity_preflight = (
            "melix.strict_install_mode" in ext
            or ("melix.install_mode" in ext and ext.get("melix.install_mode", "").strip().lower() == "strict")
        )
        if self._is_managed_hub_repo_import(ext):
            if strict_integrity_preflight:
                self._raise_if_strict_integrity_missing(
                    request=request,
                    job_id=job_id,
                    output_dir=output_dir,
                    state_path=output_dir / "download.state.json",
                    output_path=Path(""),
                    partial_path=Path(""),
                    selected_mirror="https://huggingface.co",
                    ext=ext,
                )
            return self._run_managed_hub_repo_import(
                request=request,
                job_id=job_id,
                output_dir=output_dir,
                ext=ext,
            )

        output_filename = self._output_filename(ext)
        output_path = output_dir / output_filename
        partial_path = output_dir / f"{output_filename}.partial"
        state_path = output_dir / self._state_filename(ext=ext, output_filename=output_filename)
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
        cancel_after_bytes = max(0, self._int(ext.get("test_cancel_after_bytes"), default=0))
        stall_after_bytes = max(0, self._int(ext.get("test_stall_after_bytes"), default=0))
        stall_elapsed_ms = max(0, self._int(ext.get("test_stall_elapsed_ms"), default=0))
        stall_timeout_ms = max(1, self._int(ext.get("stall_timeout_ms"), default=30_000))
        request_deadline_ms = max(0, self._int(ext.get("test_request_deadline_ms"), default=0))
        slow_in_progress_ms = max(0, self._int(ext.get("test_slow_in_progress_ms"), default=0))
        deadline_progressing_enabled = request_deadline_ms > 0 and slow_in_progress_ms > request_deadline_ms

        retry_count = 0
        stall_detection_count = 0
        resume_from_bytes = self._resume_from_bytes(partial_path=partial_path, total_bytes=total_bytes)
        resume_used = resume_from_bytes > 0
        manifest_context = self._manifest_context(
            request=request,
            job_id=job_id,
            output_dir=output_dir,
            output_path=output_path,
            partial_path=partial_path,
            state_path=state_path,
            selected_mirror=selected_mirror,
            ext=ext,
        )
        if strict_integrity_preflight:
            self._raise_if_strict_integrity_missing(
                request=request,
                job_id=job_id,
                output_dir=output_dir,
                state_path=state_path,
                output_path=output_path,
                partial_path=partial_path,
                selected_mirror=selected_mirror,
                ext=ext,
            )
        snapshots: list[DownloadSnapshot] = [
            self._snapshot(
                manifest_context=manifest_context,
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
                            deadline_progressing = deadline_progressing_enabled and downloaded_bytes < total_bytes
                            snapshots.append(
                                self._snapshot(
                                    manifest_context=manifest_context,
                                    status="in_progress" if deadline_progressing else "running",
                                    terminal_state="in_progress" if deadline_progressing else "running",
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
                                    manifest_payload=self._build_manifest_payload(
                                        manifest_context=manifest_context,
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
                                    manifest_payload=self._build_manifest_payload(
                                        manifest_context=manifest_context,
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
                            if cancel_after_bytes and downloaded_bytes >= cancel_after_bytes:
                                terminal_json = self._terminal_manifest_json(
                                    self._build_manifest_payload(
                                        manifest_context=manifest_context,
                                        status="cancelled",
                                        terminal_state="cancelled",
                                        stage="download",
                                        pct=0.0 if total_bytes == 0 else downloaded_bytes / total_bytes,
                                        downloaded_bytes=downloaded_bytes,
                                        total_bytes=total_bytes,
                                        retry_count=retry_count,
                                        resume_used=resume_used,
                                        resume_from_bytes=resume_from_bytes,
                                        stall_detection_count=stall_detection_count,
                                        stall_reason="",
                                    ),
                                    status="cancelled",
                                )
                                raise ModelOperationError(
                                    code="download_cancelled",
                                    message="Download was cancelled before completion.",
                                    details={"state_json": terminal_json},
                                )

                os.replace(os.fspath(partial_path), os.fspath(output_path))
                snapshots.append(
                    self._snapshot(
                        manifest_context=manifest_context,
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
                        exc.manifest_payload,
                        status="failed",
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
                        exc.manifest_payload,
                        status="stalled",
                    )
                    raise ModelOperationError(
                        code="download_stalled",
                        message="Download stalled without progress.",
                        details={"state_json": terminal_json},
                    ) from exc
                retry_count += 1

    def _run_managed_hub_repo_import(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        output_dir: Path,
        ext: dict[str, str],
    ) -> DownloadPipelineResult:
        repo_id = ext.get("melix.hf_repo_id", "").strip() or request.source_model.strip()
        if "/" not in repo_id:
            raise ModelOperationError(
                code="invalid_argument",
                message="managed hub import requires melix.hf_repo_id in org/repo format.",
            )
        revision = ext.get("melix.hf_revision", "").strip() or "main"

        source_dir = self._resolve_managed_hub_source_path(output_dir=output_dir, ext=ext, repo_id=repo_id, revision=revision)
        total_bytes = self._directory_size(source_dir)
        state_path = output_dir / "download.state.json"
        manifest_json = self._build_managed_import_manifest_json(
            request=request,
            job_id=job_id,
            output_dir=output_dir,
            output_path=source_dir,
            runtime_model_path=source_dir,
            state_path=state_path,
            repo_id=repo_id,
            revision=revision,
            total_bytes=total_bytes,
        )
        return DownloadPipelineResult(
            output_path=source_dir,
            snapshots=[
                DownloadSnapshot(stage="prepare", pct=0.0, manifest_json=manifest_json),
                DownloadSnapshot(stage="materialize", pct=1.0, manifest_json=manifest_json),
            ],
        )

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
        for mirror in ext.get("mirror_urls", "").split(","):
            mirror = mirror.strip()
            if mirror:
                return mirror
        return "https://huggingface.co"

    @staticmethod
    def _output_filename(ext: dict[str, str]) -> str:
        raw_name = ext.get("output_filename", "").strip() or "download.artifact"
        name = Path(raw_name).name
        return name or "download.artifact"

    @staticmethod
    def _state_filename(*, ext: dict[str, str], output_filename: str) -> str:
        if not ext.get("output_filename", "").strip():
            return "download.state.json"
        return f"{output_filename}.state.json"

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
                "ext": DownloadPipeline._public_ext(ext),
            },
            sort_keys=True,
        ).encode("utf-8")
        synthetic_source.write_bytes(payload)
        return synthetic_source

    @staticmethod
    def _is_managed_hub_repo_import(ext: dict[str, str]) -> bool:
        return (
            ext.get("melix.managed_import", "").strip().lower() in {"1", "true", "yes", "on"}
            and ext.get("melix.source_kind", "").strip() == "hub_repo"
        )

    def _resolve_managed_hub_source_path(
        self,
        *,
        output_dir: Path,
        ext: dict[str, str],
        repo_id: str,
        revision: str,
    ) -> Path:
        source_path_raw = ext.get("source_path", "").strip()
        if source_path_raw:
            source_path = Path(source_path_raw).expanduser().resolve()
            if source_path.is_dir():
                return source_path
            raise ModelOperationError(
                code="invalid_argument",
                message="managed hub import requires ext.source_path to be a directory snapshot.",
            )

        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise ModelOperationError(
                code="unavailable",
                message="huggingface_hub is required for managed hub imports.",
            ) from exc

        kwargs: dict[str, object] = {
            "repo_id": repo_id,
            "revision": revision.strip() or None,
            "cache_dir": os.fspath(self._default_huggingface_cache_root()),
        }
        token = self._huggingface_token(ext)
        if token:
            kwargs["token"] = token

        try:
            downloaded = snapshot_download(**kwargs)
        except Exception as exc:
            if self._is_huggingface_auth_failure(exc):
                raise ModelOperationError(
                    code="hf_auth_failed",
                    message=_HF_AUTH_FAILED_MESSAGE,
                ) from exc
            if self._is_huggingface_hub_failure(exc):
                raise ModelOperationError(
                    code="unavailable",
                    message=f"managed hub import failed for {repo_id}: {exc}",
                ) from exc
            raise
        return Path(downloaded).resolve()

    def _build_managed_import_manifest_json(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        output_dir: Path,
        output_path: Path,
        runtime_model_path: Path,
        state_path: Path,
        repo_id: str,
        revision: str,
        total_bytes: int,
    ) -> str:
        ext = dict(request.ext)
        public_ext = self._public_ext(request.ext)
        config_payload = self._load_model_config_payload(runtime_model_path)
        draft_metadata = dflash_draft_metadata(config_payload)
        payload = {
            "schema_version": "melix.download_job.v1",
            "job_id": job_id,
            "operation": "download",
            "operation_id": self._operation_id(request=request, ext=ext),
            "target_scope": self._target_scope(request=request, ext=ext),
            "operation_kind": self._operation_kind(ext),
            "attempts": 1,
            "timeout_ms": max(0, self._int(ext.get("test_request_deadline_ms") or ext.get("timeout_ms"), default=0)),
            "retry_after_ms": max(0, self._int(ext.get("retry_after_ms") or ext.get("test_request_deadline_ms"), default=0)),
            "last_error": "",
            "artifact_integrity": self._artifact_integrity_receipt(ext=public_ext, status="passed"),
            "model_id": repo_id,
            "managed_model_path": str(output_path),
            "source_model": request.source_model,
            "output_dir": str(output_dir),
            "status": "completed",
            "terminal_state": "completed",
            "stage": "materialize",
            "pct": 1.0,
            "source_path": request.ext.get("source_path", ""),
            "output_path": str(output_path),
            "partial_path": "",
            "state_path": str(state_path),
            "selected_mirror": "https://huggingface.co",
            "downloaded_bytes": total_bytes,
            "total_bytes": total_bytes,
            "resume_used": False,
            "resume_from_bytes": 0,
            "retry_count": 0,
            "stall_detection_count": 0,
            "stall_reason": "",
            "ext": {
                **public_ext,
                "melix.hf_repo_id": repo_id,
                "melix.hf_revision": revision,
                "melix.source_kind": "hub_repo",
                "melix.source_locator": repo_id,
                "melix.managed_import": "true",
                "melix.model_path": str(runtime_model_path),
                **draft_metadata,
            },
            "metrics": {
                "download.resume_success_rate": 0.0,
                "download.retry_count": 0,
                "download.stall_detection_count": 0,
            },
        }
        self._write_json_atomically(state_path, payload)
        return json.dumps(payload, sort_keys=True)

    @staticmethod
    def _directory_size(path: Path) -> int:
        total_bytes = 0
        stack = [os.fspath(path)]
        append_directory = stack.append
        pop_directory = stack.pop
        scandir = os.scandir
        is_dir = os.DirEntry.is_dir
        is_file = os.DirEntry.is_file
        stat_entry = os.DirEntry.stat
        while stack:
            current = pop_directory()
            with scandir(current) as entries:
                for entry in entries:
                    if is_dir(entry, follow_symlinks=False):
                        append_directory(entry.path)
                        continue
                    if is_file(entry, follow_symlinks=False):
                        total_bytes += stat_entry(entry, follow_symlinks=False).st_size
        return total_bytes

    @staticmethod
    def _load_model_config_payload(model_dir: Path) -> dict[str, Any]:
        config_path = model_dir / "config.json"
        if not config_path.is_file():
            return {}
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _is_huggingface_hub_failure(exc: Exception) -> bool:
        module = type(exc).__module__
        return module.startswith("huggingface_hub") or module.startswith("requests")

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
        manifest_context: _DownloadManifestContext,
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
        manifest_payload = self._build_manifest_payload(
            manifest_context=manifest_context,
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
        manifest_json = self._write_manifest_json(manifest_context.state_path, manifest_payload)
        return DownloadSnapshot(stage=stage, pct=pct, manifest_json=manifest_json)

    def _manifest_context(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        output_dir: Path,
        output_path: Path,
        partial_path: Path,
        state_path: Path,
        selected_mirror: str,
        ext: dict[str, str],
    ) -> _DownloadManifestContext:
        public_ext = self._public_ext(request.ext)
        receipt_enabled = self.uses_operation_receipt(ext)
        receipt_payload: dict[str, Any] = {}
        if receipt_enabled:
            receipt_payload = {
                "operation_id": self._operation_id(request=request, ext=ext),
                "target_scope": self._target_scope(request=request, ext=ext),
                "operation_kind": self._operation_kind(ext),
                "timeout_ms": max(0, self._int(ext.get("test_request_deadline_ms") or ext.get("timeout_ms"), default=0)),
                "retry_after_ms": max(0, self._int(ext.get("retry_after_ms") or ext.get("test_request_deadline_ms"), default=0)),
                "last_error": "",
            }
        return _DownloadManifestContext(
            state_path=state_path,
            base_payload={
                "schema_version": "melix.download_job.v1",
                "job_id": job_id,
                "operation": "download",
                **receipt_payload,
                "source_model": request.source_model,
                "output_dir": str(output_dir),
                "source_path": request.ext.get("source_path", ""),
                "output_path": str(output_path),
                "partial_path": str(partial_path),
                "state_path": str(state_path),
                "selected_mirror": selected_mirror,
                "ext": public_ext,
            },
            pending_artifact_integrity=(
                self._artifact_integrity_receipt(ext=public_ext, status="pending")
                if receipt_enabled
                else None
            ),
            passed_artifact_integrity=(
                self._artifact_integrity_receipt(ext=public_ext, status="passed")
                if receipt_enabled
                else None
            ),
        )

    @staticmethod
    def _build_manifest_payload(
        *,
        manifest_context: _DownloadManifestContext,
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
    ) -> dict[str, Any]:
        payload = dict(manifest_context.base_payload)
        payload.update(
            {
            "status": status,
            "terminal_state": terminal_state,
            "stage": stage,
            "pct": round(pct, 6),
            "downloaded_bytes": downloaded_bytes,
            "total_bytes": total_bytes,
            "resume_used": resume_used,
            "resume_from_bytes": resume_from_bytes,
            "retry_count": retry_count,
            "stall_detection_count": stall_detection_count,
            "stall_reason": stall_reason,
            "metrics": {
                "download.resume_success_rate": 1.0 if resume_used and terminal_state == "completed" else 0.0,
                "download.retry_count": retry_count,
                "download.stall_detection_count": stall_detection_count,
            },
            }
        )
        if manifest_context.pending_artifact_integrity is not None:
            payload["attempts"] = retry_count + 1
            payload["artifact_integrity"] = (
                manifest_context.passed_artifact_integrity
                if terminal_state == "completed"
                else manifest_context.pending_artifact_integrity
            )
        return payload

    @staticmethod
    def _write_manifest_json(state_path: Path, payload: dict[str, Any]) -> str:
        DownloadPipeline._write_json_atomically(state_path, payload)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _terminal_manifest_json(manifest_payload: dict[str, Any], *, status: str) -> str:
        payload = dict(manifest_payload)
        payload["status"] = status
        if status == "failed":
            payload["terminal_state"] = "failed"
            payload["last_error"] = payload.get("stall_reason") or "download_failed"
            payload["artifact_integrity"] = DownloadPipeline._artifact_integrity_receipt(
                ext=payload.get("ext", {}),
                status="failed",
                failure_reason=str(payload["last_error"]),
            )
        elif status == "stalled":
            payload["terminal_state"] = "stalled"
            payload["last_error"] = payload.get("stall_reason") or "download_stalled"
            payload["artifact_integrity"] = DownloadPipeline._artifact_integrity_receipt(
                ext=payload.get("ext", {}),
                status="failed",
                failure_reason=str(payload["last_error"]),
            )
        elif status == "cancelled":
            payload["terminal_state"] = "cancelled"
            payload["last_error"] = "download_cancelled"
            payload["artifact_integrity"] = DownloadPipeline._artifact_integrity_receipt(
                ext=payload.get("ext", {}),
                status="failed",
                failure_reason="download_cancelled",
            )
        return DownloadPipeline._write_manifest_json(Path(str(payload["state_path"])), payload)

    @classmethod
    def operation_identity(cls, request: maintenance_pb2.ConvertModelRequest) -> tuple[str, str, str]:
        ext = dict(request.ext)
        operation_kind = cls._operation_kind(ext)
        target_scope = cls._target_scope(request=request, ext=ext)
        operation_id = cls._operation_id(request=request, ext=ext)
        return operation_id, target_scope, operation_kind

    @staticmethod
    def _operation_kind(ext: dict[str, str]) -> str:
        return ext.get("melix.operation_kind", "").strip() or "managed_model_install"

    @classmethod
    def _operation_id(
        cls,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        ext: dict[str, str],
    ) -> str:
        explicit = ext.get("melix.operation_id", "").strip()
        if explicit:
            return explicit
        operation_kind = cls._operation_kind(ext)
        target_scope = cls._target_scope(request=request, ext=ext)
        digest = hashlib.sha256(f"{operation_kind}\0{target_scope}".encode("utf-8")).hexdigest()[:16]
        return f"{operation_kind}:{digest}"

    @staticmethod
    def _target_scope(
        *,
        request: maintenance_pb2.ConvertModelRequest,
        ext: dict[str, str],
    ) -> str:
        explicit = ext.get("melix.target_scope", "").strip()
        if explicit:
            return explicit
        repo_id = ext.get("melix.hf_repo_id", "").strip() or request.source_model.strip()
        revision = ext.get("melix.hf_revision", "").strip() or "main"
        if repo_id:
            return f"hub:{repo_id}@{revision}"
        source_path = ext.get("source_path", "").strip()
        if source_path:
            return f"local:{Path(source_path).expanduser().resolve()}"
        return request.source_model.strip() or "download"

    @staticmethod
    def uses_operation_receipt(ext: dict[str, str]) -> bool:
        return (
            ext.get("melix.managed_import", "").strip().lower() in {"1", "true", "yes", "on"}
            or ext.get("melix.operation_id", "").strip() != ""
            or ext.get("melix.operation_kind", "").strip() != ""
            or ext.get("melix.target_scope", "").strip() != ""
            or ext.get("melix.strict_install_mode", "").strip() != ""
            or ext.get("melix.install_mode", "").strip().lower() == "strict"
            or ext.get("melix.artifact_digest", "").strip() != ""
            or ext.get("artifact_digest", "").strip() != ""
            or ext.get("sha256", "").strip() != ""
            or ext.get("test_request_deadline_ms", "").strip() != ""
        )

    @staticmethod
    def _artifact_integrity_receipt(
        *,
        ext: dict[str, Any],
        status: str,
        failure_reason: str = "",
    ) -> dict[str, Any]:
        digest = str(
            ext.get("melix.artifact_digest")
            or ext.get("artifact_digest")
            or ext.get("sha256")
            or ""
        )
        return {
            "verification_mode": str(ext.get("melix.verification_mode") or "receipt_fixture"),
            "policy_present": bool(digest or status != "failed"),
            "digest": digest,
            "checked_at": str(ext.get("melix.integrity_checked_at") or "not_recorded"),
            "failure_reason": failure_reason,
            "status": status,
        }

    @classmethod
    def _raise_if_strict_integrity_missing(
        cls,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        output_dir: Path,
        state_path: Path,
        output_path: Path,
        partial_path: Path,
        selected_mirror: str,
        ext: dict[str, str],
    ) -> None:
        if not cls._strict_install_mode(ext) or cls._artifact_digest(ext):
            return
        public_ext = cls._public_ext(ext)
        operation_id, target_scope, operation_kind = cls.operation_identity(request)
        payload = {
            "schema_version": "melix.download_job.v1",
            "job_id": job_id,
            "operation": "download",
            "operation_id": operation_id,
            "target_scope": target_scope,
            "operation_kind": operation_kind,
            "attempts": 1,
            "timeout_ms": max(0, cls._int(ext.get("test_request_deadline_ms") or ext.get("timeout_ms"), default=0)),
            "retry_after_ms": max(0, cls._int(ext.get("retry_after_ms") or ext.get("test_request_deadline_ms"), default=0)),
            "last_error": "missing_artifact_digest",
            "artifact_integrity": cls._artifact_integrity_receipt(
                ext=public_ext,
                status="failed",
                failure_reason="missing_artifact_digest",
            ),
            "source_model": request.source_model,
            "output_dir": str(output_dir),
            "status": "failed",
            "terminal_state": "failed",
            "stage": "strict_preflight",
            "pct": 0.0,
            "source_path": request.ext.get("source_path", ""),
            "output_path": str(output_path) if str(output_path) != "." else "",
            "partial_path": str(partial_path) if str(partial_path) != "." else "",
            "state_path": str(state_path),
            "selected_mirror": selected_mirror,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "resume_used": False,
            "resume_from_bytes": 0,
            "retry_count": 0,
            "stall_detection_count": 0,
            "stall_reason": "",
            "ext": public_ext,
            "metrics": {
                "download.resume_success_rate": 0.0,
                "download.retry_count": 0,
                "download.stall_detection_count": 0,
            },
        }
        state_json = cls._write_manifest_json(state_path, payload)
        raise ModelOperationError(
            code="artifact_integrity_required",
            message="Strict managed artifact installs require an artifact digest before activation.",
            details={
                "state_json": state_json,
                "failure_reason": "missing_artifact_digest",
            },
        )

    @staticmethod
    def _strict_install_mode(ext: dict[str, str]) -> bool:
        raw_flag = ext.get("melix.strict_install_mode", "").strip().lower()
        if raw_flag in {"1", "true", "yes", "on"}:
            return True
        return ext.get("melix.install_mode", "").strip().lower() == "strict"

    @staticmethod
    def _artifact_digest(ext: dict[str, Any]) -> str:
        return str(
            ext.get("melix.artifact_digest")
            or ext.get("artifact_digest")
            or ext.get("sha256")
            or ""
        ).strip()

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
                json.dump(payload, temp_file, sort_keys=True, separators=(",", ":"))
            os.replace(os.fspath(temp_path), os.fspath(path))
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _default_huggingface_cache_root() -> Path:
        return (Path.home() / ".cache" / "huggingface" / "hub").resolve()

    @staticmethod
    def _huggingface_token(ext: dict[str, str]) -> str:
        for key in ("melix.hf_token", "hf_token", "HUGGINGFACE_HUB_TOKEN", "HF_TOKEN"):
            token = ext.get(key, "").strip()
            if token:
                return token
        return ""

    @staticmethod
    def _public_ext(ext: dict[str, str] | Any) -> dict[str, str]:
        return {
            str(key): str(value)
            for key, value in dict(ext).items()
            if str(key) not in _HF_TOKEN_EXT_KEYS and "token" not in str(key).lower()
        }

    @staticmethod
    def _is_huggingface_auth_failure(exc: Exception) -> bool:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {401, 403}:
            return True
        message = str(exc).lower()
        return "401" in message or "403" in message or "unauthorized" in message or "forbidden" in message
