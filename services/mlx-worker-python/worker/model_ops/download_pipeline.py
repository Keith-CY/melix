from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
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
_PARTIAL_RESUME_ELIGIBLE_STATES = frozenset(
    {"running", "retrying", "in_progress", "failed", "stalled", "cancelled"}
)


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
    transport_receipt_enabled: bool
    requested_transport: str
    effective_transport: str
    fallback_reason: str
    chunk_resume_mode: str
    stale_partial_removed: bool
    stale_partial_bytes: int
    stale_partial_age_ms: int


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
            or ("melix.install_mode" in ext and self._ext_text(ext, "melix.install_mode").lower() == "strict")
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
        stale_partial_removed, stale_partial_bytes, stale_partial_age_ms = self._sweep_stale_partial(
            partial_path=partial_path,
            total_bytes=total_bytes,
            ext=ext,
        )
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
            stale_partial_removed=stale_partial_removed,
            stale_partial_bytes=stale_partial_bytes,
            stale_partial_age_ms=stale_partial_age_ms,
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
        self._raise_if_empty_unknown_size_body(
            manifest_context=manifest_context,
            ext=ext,
            total_bytes=total_bytes,
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

                completed_payload = self._build_manifest_payload(
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
                if self._artifact_digest(completed_payload.get("ext", {})):
                    completed_payload["artifact_integrity"] = self._verified_artifact_integrity_receipt(
                        artifact_path=partial_path,
                        ext=completed_payload.get("ext", {}),
                        status="passed",
                    )
                    self._raise_if_strict_integrity_mismatch(
                        manifest_payload=completed_payload,
                        partial_path=partial_path,
                        ext=ext,
                    )
                companion_declarations = (
                    self._companion_manifest(ext) if "melix.companion_manifest" in ext else []
                )
                if companion_declarations:
                    self._raise_if_required_companions_missing(
                        manifest_payload=completed_payload,
                        primary_artifact=output_path,
                        companion_search_artifact=source_path,
                        primary_staging_path=partial_path,
                        ext=ext,
                        declarations=companion_declarations,
                    )
                os.replace(os.fspath(partial_path), os.fspath(output_path))
                if companion_declarations:
                    completed_payload["artifact_companions"] = self._artifact_companions_receipt(
                        primary_artifact=output_path,
                        companion_search_artifact=source_path,
                        ext=ext,
                        declarations=companion_declarations,
                        stage=True,
                    )
                manifest_json = self._write_manifest_json(state_path, completed_payload)
                snapshots.append(DownloadSnapshot(stage="download", pct=1.0, manifest_json=manifest_json))
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
        repo_id = self._ext_text(ext, "melix.hf_repo_id") or request.source_model.strip()
        if "/" not in repo_id:
            raise ModelOperationError(
                code="invalid_argument",
                message="managed hub import requires melix.hf_repo_id in org/repo format.",
            )
        revision = self._ext_text(ext, "melix.hf_revision") or "main"

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

    @classmethod
    def _sweep_stale_partial(
        cls,
        *,
        partial_path: Path,
        total_bytes: int,
        ext: dict[str, str],
    ) -> tuple[bool, int, int]:
        max_age_ms = max(
            0,
            cls._int(
                ext.get("melix.stale_partial_after_ms") or ext.get("stale_partial_after_ms"),
                default=0,
            ),
        )
        if max_age_ms <= 0 or not partial_path.exists():
            return False, 0, 0

        partial_bytes, partial_age_ms = cls._partial_file_state(partial_path)
        if partial_bytes <= 0 or (total_bytes > 0 and partial_bytes > total_bytes):
            partial_path.unlink(missing_ok=True)
            return True, partial_bytes, partial_age_ms
        if partial_age_ms >= max_age_ms:
            partial_path.unlink(missing_ok=True)
            return True, partial_bytes, partial_age_ms
        return False, 0, 0

    @staticmethod
    def _partial_file_state(partial_path: Path) -> tuple[int, int]:
        if not partial_path.exists():
            return 0, 0
        stat_result = partial_path.stat()
        return stat_result.st_size, max(0, int((time.time() - stat_result.st_mtime) * 1000))

    @staticmethod
    def _selected_mirror(ext: dict[str, Any]) -> str:
        explicit = DownloadPipeline._ext_text(ext, "mirror_url")
        if explicit:
            return explicit
        for mirror in DownloadPipeline._ext_text(ext, "mirror_urls").split(","):
            mirror = mirror.strip()
            if mirror:
                return mirror
        return "https://huggingface.co"

    @staticmethod
    def _output_filename(ext: dict[str, Any]) -> str:
        raw_name = DownloadPipeline._ext_text(ext, "output_filename") or "download.artifact"
        name = Path(raw_name).name
        return name or "download.artifact"

    @staticmethod
    def _state_filename(*, ext: dict[str, Any], output_filename: str) -> str:
        if not DownloadPipeline._ext_text(ext, "output_filename"):
            return "download.state.json"
        return f"{output_filename}.state.json"

    @staticmethod
    def _resolve_source_path(
        *,
        request: maintenance_pb2.ConvertModelRequest,
        output_dir: Path,
        ext: dict[str, Any],
    ) -> Path:
        source_path_raw = DownloadPipeline._ext_text(ext, "source_path")
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
    def _is_managed_hub_repo_import(ext: dict[str, Any]) -> bool:
        return (
            DownloadPipeline._ext_text(ext, "melix.managed_import").lower() in {"1", "true", "yes", "on"}
            and DownloadPipeline._ext_text(ext, "melix.source_kind") == "hub_repo"
        )

    def _resolve_managed_hub_source_path(
        self,
        *,
        output_dir: Path,
        ext: dict[str, Any],
        repo_id: str,
        revision: str,
    ) -> Path:
        source_path_raw = self._ext_text(ext, "source_path")
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
        requested_transport, effective_transport, fallback_reason, chunk_resume_mode = (
            self._transport_selection(public_ext)
        )
        artifact_integrity = self._artifact_integrity_receipt(ext=public_ext, status="passed")
        if self._artifact_digest(public_ext):
            artifact_integrity = self._verified_directory_artifact_integrity_receipt(
                artifact_path=runtime_model_path,
                ext=public_ext,
                status="passed",
            )
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
            "artifact_integrity": artifact_integrity,
            "artifact_transport_receipt": self._artifact_transport_receipt(
                requested_transport=requested_transport,
                effective_transport=effective_transport,
                fallback_reason=fallback_reason,
                chunk_resume_mode=chunk_resume_mode,
                planned_bytes=total_bytes,
                written_bytes=total_bytes,
                selected_mirror="https://huggingface.co",
                integrity_decision="accepted",
                status="completed",
            ),
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
            "partial_bytes": 0,
            "partial_age_ms": 0,
            "resume_eligible": False,
            "stale_partial_removed": False,
            "partial_lifecycle": "completed_activated",
            "activated": True,
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
        self._raise_if_strict_integrity_mismatch(
            manifest_payload=payload,
            partial_path=Path(""),
            ext=ext,
        )
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

    @staticmethod
    def _ext_text(ext: dict[str, Any], key: str, default: str = "") -> str:
        value = ext.get(key, default)
        if value is None:
            return default
        return str(value).strip()

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
        stale_partial_removed: bool,
        stale_partial_bytes: int,
        stale_partial_age_ms: int,
    ) -> _DownloadManifestContext:
        public_ext = self._public_ext(request.ext)
        receipt_enabled = self.uses_operation_receipt(ext)
        (
            requested_transport,
            effective_transport,
            fallback_reason,
            chunk_resume_mode,
        ) = self._transport_selection(public_ext)
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
            transport_receipt_enabled=self._transport_receipt_enabled(ext),
            requested_transport=requested_transport,
            effective_transport=effective_transport,
            fallback_reason=fallback_reason,
            chunk_resume_mode=chunk_resume_mode,
            stale_partial_removed=stale_partial_removed,
            stale_partial_bytes=stale_partial_bytes,
            stale_partial_age_ms=stale_partial_age_ms,
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
            payload.update(
                DownloadPipeline._partial_lifecycle_receipt(
                    total_bytes=total_bytes,
                    downloaded_bytes=downloaded_bytes,
                    terminal_state=terminal_state,
                    stale_partial_removed=manifest_context.stale_partial_removed,
                    stale_partial_bytes=manifest_context.stale_partial_bytes,
                    stale_partial_age_ms=manifest_context.stale_partial_age_ms,
                )
            )
        if manifest_context.transport_receipt_enabled:
            payload["artifact_transport_receipt"] = DownloadPipeline._artifact_transport_receipt(
                requested_transport=manifest_context.requested_transport,
                effective_transport=manifest_context.effective_transport,
                fallback_reason=manifest_context.fallback_reason,
                chunk_resume_mode=manifest_context.chunk_resume_mode,
                planned_bytes=total_bytes,
                written_bytes=downloaded_bytes,
                selected_mirror=str(payload.get("selected_mirror", "")),
                integrity_decision=(
                    "accepted" if terminal_state == "completed" else "pending"
                ),
                status="completed" if terminal_state == "completed" else status,
            )
        return payload

    @staticmethod
    def _partial_lifecycle_receipt(
        *,
        total_bytes: int,
        downloaded_bytes: int,
        terminal_state: str,
        stale_partial_removed: bool = False,
        stale_partial_bytes: int = 0,
        stale_partial_age_ms: int = 0,
    ) -> dict[str, Any]:
        partial_bytes = 0
        partial_age_ms = 0
        if downloaded_bytes > 0 and (total_bytes == 0 or downloaded_bytes < total_bytes):
            partial_bytes = downloaded_bytes
        stale_removal_only = stale_partial_removed and partial_bytes <= 0 and terminal_state != "completed"
        if stale_removal_only:
            partial_bytes = stale_partial_bytes
            partial_age_ms = stale_partial_age_ms

        activated = terminal_state == "completed"
        resume_eligible = (
            partial_bytes > 0
            and not activated
            and not stale_removal_only
            and (total_bytes == 0 or partial_bytes < total_bytes)
            and terminal_state in _PARTIAL_RESUME_ELIGIBLE_STATES
        )

        if activated:
            partial_bytes = 0
            partial_age_ms = 0
            lifecycle = "completed_activated"
        elif stale_removal_only:
            resume_eligible = False
            lifecycle = "stale_removed"
        elif partial_bytes <= 0:
            lifecycle = "none"
        elif terminal_state == "cancelled":
            lifecycle = "cancelled_kept_for_resume"
        elif terminal_state == "stalled":
            lifecycle = "stalled_kept_for_resume"
        elif terminal_state == "failed":
            lifecycle = "failed_kept_for_resume"
        else:
            lifecycle = "resume_candidate" if resume_eligible else "partial_present"

        return {
            "partial_bytes": partial_bytes,
            "partial_age_ms": partial_age_ms,
            "resume_eligible": resume_eligible,
            "stale_partial_removed": stale_partial_removed,
            "partial_lifecycle": lifecycle,
            "activated": activated,
        }

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
        payload.update(
            DownloadPipeline._partial_lifecycle_receipt(
                total_bytes=int(payload.get("total_bytes", 0)),
                downloaded_bytes=int(payload.get("downloaded_bytes", 0)),
                terminal_state=str(payload.get("terminal_state", payload.get("status", ""))),
                stale_partial_removed=bool(payload.get("stale_partial_removed", False)),
                stale_partial_bytes=int(payload.get("partial_bytes", 0)),
                stale_partial_age_ms=int(payload.get("partial_age_ms", 0)),
            )
        )
        DownloadPipeline._refresh_terminal_transport_receipt(payload, status=status)
        return DownloadPipeline._write_manifest_json(Path(str(payload["state_path"])), payload)

    @classmethod
    def operation_identity(cls, request: maintenance_pb2.ConvertModelRequest) -> tuple[str, str, str]:
        ext = dict(request.ext)
        operation_kind = cls._operation_kind(ext)
        target_scope = cls._target_scope(request=request, ext=ext)
        operation_id = cls._operation_id(request=request, ext=ext)
        return operation_id, target_scope, operation_kind

    @staticmethod
    def _operation_kind(ext: dict[str, Any]) -> str:
        return DownloadPipeline._ext_text(ext, "melix.operation_kind") or "managed_model_install"

    @classmethod
    def _operation_id(
        cls,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        ext: dict[str, Any],
    ) -> str:
        explicit = cls._ext_text(ext, "melix.operation_id")
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
        ext: dict[str, Any],
    ) -> str:
        explicit = DownloadPipeline._ext_text(ext, "melix.target_scope")
        if explicit:
            return explicit
        repo_id = DownloadPipeline._ext_text(ext, "melix.hf_repo_id") or request.source_model.strip()
        revision = DownloadPipeline._ext_text(ext, "melix.hf_revision") or "main"
        if repo_id:
            return f"hub:{repo_id}@{revision}"
        source_path = DownloadPipeline._ext_text(ext, "source_path")
        if source_path:
            return f"local:{Path(source_path).expanduser().resolve()}"
        return request.source_model.strip() or "download"

    @staticmethod
    def uses_operation_receipt(ext: dict[str, Any]) -> bool:
        return (
            DownloadPipeline._ext_text(ext, "melix.managed_import").lower() in {"1", "true", "yes", "on"}
            or DownloadPipeline._ext_text(ext, "melix.operation_id") != ""
            or DownloadPipeline._ext_text(ext, "melix.operation_kind") != ""
            or DownloadPipeline._ext_text(ext, "melix.target_scope") != ""
            or DownloadPipeline._ext_text(ext, "melix.strict_install_mode") != ""
            or DownloadPipeline._ext_text(ext, "melix.install_mode").lower() == "strict"
            or DownloadPipeline._ext_text(ext, "melix.artifact_digest") != ""
            or DownloadPipeline._ext_text(ext, "artifact_digest") != ""
            or DownloadPipeline._ext_text(ext, "sha256") != ""
            or DownloadPipeline._ext_text(ext, "test_request_deadline_ms") != ""
        )

    @classmethod
    def _artifact_integrity_receipt(
        cls,
        *,
        ext: dict[str, Any],
        status: str,
        failure_reason: str = "",
        actual_digest: str = "",
        checked_at: str = "",
    ) -> dict[str, Any]:
        digest = cls._artifact_digest(ext)
        normalized_actual_digest = cls._normalize_sha256_digest(actual_digest)
        verification_mode = str(ext.get("melix.verification_mode") or "receipt_fixture")
        if cls._sha256_digest_hex(digest) or cls._sha256_digest_hex(normalized_actual_digest):
            verification_mode = "sha256"
        receipt = {
            "verification_mode": verification_mode,
            "policy_present": bool(digest or status != "failed"),
            "digest": digest,
            "checked_at": checked_at or str(ext.get("melix.integrity_checked_at") or "not_recorded"),
            "failure_reason": failure_reason,
            "status": status,
        }
        if digest:
            receipt["actual_digest"] = normalized_actual_digest
        return receipt

    @classmethod
    def _verified_artifact_integrity_receipt(
        cls,
        *,
        artifact_path: Path,
        ext: dict[str, Any],
        status: str,
        failure_reason: str = "",
    ) -> dict[str, Any]:
        actual_digest = f"sha256:{cls._sha256_file(artifact_path)}" if cls._artifact_digest(ext) else ""
        return cls._artifact_integrity_receipt(
            ext=ext,
            status=status,
            failure_reason=failure_reason,
            actual_digest=actual_digest,
            checked_at=cls._utc_now_iso8601(),
        )

    @classmethod
    def _verified_directory_artifact_integrity_receipt(
        cls,
        *,
        artifact_path: Path,
        ext: dict[str, Any],
        status: str,
        failure_reason: str = "",
    ) -> dict[str, Any]:
        actual_digest = f"sha256:{cls._sha256_directory_snapshot(artifact_path)}" if cls._artifact_digest(ext) else ""
        return cls._artifact_integrity_receipt(
            ext=ext,
            status=status,
            failure_reason=failure_reason,
            actual_digest=actual_digest,
            checked_at=cls._utc_now_iso8601(),
        )

    @classmethod
    def _raise_if_strict_integrity_mismatch(
        cls,
        *,
        manifest_payload: dict[str, Any],
        partial_path: Path,
        ext: dict[str, str],
    ) -> None:
        if not cls._strict_install_mode(ext):
            return
        artifact_integrity = manifest_payload.get("artifact_integrity")
        if not isinstance(artifact_integrity, dict):
            return
        declared_digest = str(artifact_integrity.get("digest", "")).strip()
        actual_digest = str(artifact_integrity.get("actual_digest", "")).strip()
        declared_sha256 = cls._sha256_digest_hex(declared_digest)
        actual_sha256 = cls._sha256_digest_hex(actual_digest)
        if not declared_sha256:
            failure_reason = "unsupported_artifact_digest"
            payload = cls._failed_integrity_payload(
                manifest_payload=manifest_payload,
                partial_path=partial_path,
                failure_reason=failure_reason,
            )
            state_json = cls._write_manifest_json(Path(str(payload["state_path"])), payload)
            raise ModelOperationError(
                code="artifact_integrity_unsupported",
                message="Strict managed artifact installs require a supported SHA-256 digest before activation.",
                details={
                    "state_json": state_json,
                    "failure_reason": failure_reason,
                },
            )
        if declared_sha256 == actual_sha256:
            return

        failure_reason = "digest_mismatch"
        payload = cls._failed_integrity_payload(
            manifest_payload=manifest_payload,
            partial_path=partial_path,
            failure_reason=failure_reason,
        )
        state_json = cls._write_manifest_json(Path(str(payload["state_path"])), payload)
        raise ModelOperationError(
            code="artifact_integrity_mismatch",
            message="Strict managed artifact install digest verification failed before activation.",
            details={
                "state_json": state_json,
                "failure_reason": failure_reason,
            },
        )

    @classmethod
    def _failed_integrity_payload(
        cls,
        *,
        manifest_payload: dict[str, Any],
        partial_path: Path,
        failure_reason: str,
    ) -> dict[str, Any]:
        artifact_integrity = manifest_payload.get("artifact_integrity")
        if not isinstance(artifact_integrity, dict):
            artifact_integrity = {}
        payload = dict(manifest_payload)
        payload.update(
            {
                "status": "failed",
                "terminal_state": "failed",
                "last_error": failure_reason,
                "artifact_integrity": {
                    **artifact_integrity,
                    "failure_reason": failure_reason,
                    "status": "failed",
                },
                "activated": False,
            }
        )
        has_partial_path = str(partial_path) not in {"", "."}
        partial_bytes, partial_age_ms = (
            cls._partial_file_state(partial_path)
            if has_partial_path
            else (0, 0)
        )
        partial_lifecycle = "failed_kept_for_resume" if has_partial_path else "none"
        payload.update(
            {
                "partial_bytes": partial_bytes,
                "partial_age_ms": partial_age_ms,
                "resume_eligible": False,
                "stale_partial_removed": bool(payload.get("stale_partial_removed", False)),
                "partial_lifecycle": partial_lifecycle,
            }
        )
        return payload

    @staticmethod
    def _transport_receipt_enabled(ext: dict[str, Any]) -> bool:
        return DownloadPipeline.uses_operation_receipt(ext)

    @staticmethod
    def _transport_selection(ext: dict[str, Any]) -> tuple[str, str, str, str]:
        requested = DownloadPipeline._ext_text(ext, "melix.requested_transport") or "http_range_resume"
        effective = requested
        fallback_reason = ""
        helper_available = DownloadPipeline._ext_text(ext, "melix.transport_helper_available").lower()
        force_fallback = DownloadPipeline._ext_text(ext, "melix.force_transport_fallback").lower()

        if force_fallback in {"1", "true", "yes", "on"}:
            effective = "http_range_resume"
            fallback_reason = "user_forced_fallback"
        elif requested == "parallel_chunked" and helper_available in {"0", "false", "no", "off"}:
            effective = "http_range_resume"
            fallback_reason = "transport_helper_unavailable"

        chunk_resume_mode = "parallel_chunks" if effective == "parallel_chunked" else "range_resume"
        return requested, effective, fallback_reason, chunk_resume_mode

    @staticmethod
    def _artifact_transport_receipt(
        *,
        requested_transport: str,
        effective_transport: str,
        fallback_reason: str,
        chunk_resume_mode: str,
        planned_bytes: int,
        written_bytes: int,
        selected_mirror: str,
        integrity_decision: str,
        status: str,
    ) -> dict[str, Any]:
        progress_pct = 0.0 if planned_bytes <= 0 else written_bytes / planned_bytes
        return {
            "requested_transport": requested_transport,
            "effective_transport": effective_transport,
            "fallback_reason": fallback_reason,
            "chunk_resume_mode": chunk_resume_mode,
            "planned_bytes": planned_bytes,
            "written_bytes": written_bytes,
            "progress_pct": round(progress_pct, 6),
            "integrity_decision": integrity_decision,
            "status": status,
            "selected_mirror": selected_mirror,
        }

    @staticmethod
    def _refresh_terminal_transport_receipt(payload: dict[str, Any], *, status: str) -> None:
        receipt = payload.get("artifact_transport_receipt")
        if not isinstance(receipt, dict):
            ext = payload.get("ext", {})
            if not isinstance(ext, dict) or not DownloadPipeline._transport_receipt_enabled(ext):
                return
            requested, effective, fallback_reason, chunk_resume_mode = (
                DownloadPipeline._transport_selection(ext)
            )
        else:
            requested = str(receipt.get("requested_transport") or "http_range_resume")
            effective = str(receipt.get("effective_transport") or requested)
            fallback_reason = str(receipt.get("fallback_reason") or "")
            chunk_resume_mode = str(receipt.get("chunk_resume_mode") or "range_resume")
        integrity_decision = "cancelled" if status == "cancelled" else "rejected"
        payload["artifact_transport_receipt"] = DownloadPipeline._artifact_transport_receipt(
            requested_transport=requested,
            effective_transport=effective,
            fallback_reason=fallback_reason,
            chunk_resume_mode=chunk_resume_mode,
            planned_bytes=int(payload.get("total_bytes", 0)),
            written_bytes=int(payload.get("downloaded_bytes", 0)),
            selected_mirror=str(payload.get("selected_mirror", "")),
            integrity_decision=integrity_decision,
            status=status,
        )

    @classmethod
    def _raise_if_empty_unknown_size_body(
        cls,
        *,
        manifest_context: _DownloadManifestContext,
        ext: dict[str, Any],
        total_bytes: int,
    ) -> None:
        if total_bytes != 0:
            return
        if not cls._transport_receipt_enabled(ext):
            return
        if cls._ext_text(ext, "melix.allow_unknown_size").lower() not in {"1", "true", "yes", "on"}:
            return

        payload = cls._build_manifest_payload(
            manifest_context=manifest_context,
            status="failed",
            terminal_state="failed",
            stage="download",
            pct=0.0,
            downloaded_bytes=0,
            total_bytes=0,
            retry_count=0,
            resume_used=False,
            resume_from_bytes=0,
            stall_detection_count=0,
            stall_reason="",
        )
        payload["last_error"] = "empty_artifact_body"
        payload["artifact_integrity"] = cls._artifact_integrity_receipt(
            ext=payload.get("ext", {}),
            status="failed",
            failure_reason="empty_artifact_body",
        )
        requested, effective, _, chunk_resume_mode = cls._transport_selection(payload.get("ext", {}))
        payload["artifact_transport_receipt"] = cls._artifact_transport_receipt(
            requested_transport=requested,
            effective_transport=effective,
            fallback_reason="empty_body_unknown_size",
            chunk_resume_mode=chunk_resume_mode,
            planned_bytes=0,
            written_bytes=0,
            selected_mirror=str(payload.get("selected_mirror", "")),
            integrity_decision="rejected_empty_body",
            status="failed",
        )
        state_json = cls._write_manifest_json(manifest_context.state_path, payload)
        raise ModelOperationError(
            code="empty_artifact_body",
            message="Managed artifact download returned an empty body without a canonical size.",
            details={
                "state_json": state_json,
                "failure_reason": "empty_artifact_body",
            },
        )

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
        ext: dict[str, Any],
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
            "partial_bytes": 0,
            "partial_age_ms": 0,
            "resume_eligible": False,
            "stale_partial_removed": False,
            "partial_lifecycle": "none",
            "activated": False,
            "ext": public_ext,
            "metrics": {
                "download.resume_success_rate": 0.0,
                "download.retry_count": 0,
                "download.stall_detection_count": 0,
            },
        }
        requested_transport, effective_transport, fallback_reason, chunk_resume_mode = (
            cls._transport_selection(public_ext)
        )
        payload["artifact_transport_receipt"] = cls._artifact_transport_receipt(
            requested_transport=requested_transport,
            effective_transport=effective_transport,
            fallback_reason=fallback_reason,
            chunk_resume_mode=chunk_resume_mode,
            planned_bytes=0,
            written_bytes=0,
            selected_mirror=selected_mirror,
            integrity_decision="rejected_preflight",
            status="failed",
        )
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
    def _strict_install_mode(ext: dict[str, Any]) -> bool:
        raw_flag = DownloadPipeline._ext_text(ext, "melix.strict_install_mode").lower()
        if raw_flag in {"1", "true", "yes", "on"}:
            return True
        return DownloadPipeline._ext_text(ext, "melix.install_mode").lower() == "strict"

    @classmethod
    def _artifact_digest(cls, ext: dict[str, Any]) -> str:
        return cls._normalize_sha256_digest(
            ext.get("melix.artifact_digest")
            or ext.get("artifact_digest")
            or ext.get("sha256")
            or ""
        )

    @staticmethod
    def _normalize_sha256_digest(raw_digest: Any) -> str:
        digest = str(raw_digest or "").strip()
        if not digest:
            return ""
        lowered = digest.lower()
        hex_part = lowered.removeprefix("sha256:")
        if len(hex_part) == 64 and all(char in "0123456789abcdef" for char in hex_part):
            return f"sha256:{hex_part}"
        return digest

    @staticmethod
    def _sha256_digest_hex(digest: str) -> str:
        normalized = DownloadPipeline._normalize_sha256_digest(digest)
        if not normalized.startswith("sha256:"):
            return ""
        hex_part = normalized.removeprefix("sha256:")
        if len(hex_part) == 64 and all(char in "0123456789abcdef" for char in hex_part):
            return hex_part
        return ""

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sha256_directory_snapshot(path: Path) -> str:
        digest = hashlib.sha256()
        for relative_path, file_path, file_size in DownloadPipeline._directory_snapshot_files(path):
            digest.update(b"file\0")
            digest.update(relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(file_size).encode("ascii"))
            digest.update(b"\0")
            with open(file_path, "rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _directory_snapshot_files(path: Path) -> list[tuple[str, str, int]]:
        root_path = os.fspath(path)
        root_prefix_length = len(root_path.rstrip(os.sep)) + 1
        files: list[tuple[str, str, int]] = []
        append_file = files.append
        stack = [root_path]
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
                        relative_path = entry.path[root_prefix_length:].replace(os.sep, "/")
                        append_file(
                            (
                                relative_path,
                                entry.path,
                                stat_entry(entry, follow_symlinks=False).st_size,
                            )
                        )
        files.sort()
        return files

    @staticmethod
    def _utc_now_iso8601() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @classmethod
    def _raise_if_required_companions_missing(
        cls,
        *,
        manifest_payload: dict[str, Any],
        primary_artifact: Path,
        companion_search_artifact: Path,
        primary_staging_path: Path,
        ext: dict[str, str],
        declarations: list[dict[str, Any]] | None = None,
    ) -> None:
        receipt = cls._artifact_companions_receipt(
            primary_artifact=primary_artifact,
            companion_search_artifact=companion_search_artifact,
            ext=ext,
            declarations=declarations,
        )
        missing_required = receipt.get("missing_required", [])
        if not cls._strict_install_mode(ext) or not missing_required:
            return

        payload = dict(manifest_payload)
        payload.update(
            {
                "status": "failed",
                "terminal_state": "failed",
                "last_error": "missing_required_companion",
                "artifact_companions": receipt,
                "output_path": str(primary_artifact),
                "partial_path": str(primary_staging_path),
                "activated": False,
            }
        )
        payload.update(
            cls._partial_lifecycle_receipt(
                total_bytes=int(payload.get("total_bytes", 0)),
                downloaded_bytes=int(payload.get("downloaded_bytes", 0)),
                terminal_state="failed",
            )
        )
        state_json = cls._write_manifest_json(Path(str(payload["state_path"])), payload)
        raise ModelOperationError(
            code="artifact_companion_required",
            message="Strict managed artifact installs require declared companion artifacts before activation.",
            details={
                "state_json": state_json,
                "failure_reason": "missing_required_companion",
            },
        )

    @classmethod
    def _artifact_companions_receipt(
        cls,
        *,
        primary_artifact: Path,
        companion_search_artifact: Path | None = None,
        ext: dict[str, str],
        declarations: list[dict[str, Any]] | None = None,
        stage: bool = False,
    ) -> dict[str, Any]:
        declarations = cls._companion_manifest(ext) if declarations is None else declarations
        companion_artifacts = [
            cls._companion_artifact_receipt(
                primary_artifact=primary_artifact,
                companion_search_artifact=companion_search_artifact or primary_artifact,
                ext=ext,
                declaration=declaration,
                stage=stage,
            )
            for declaration in declarations
        ]
        missing_required = [
            str(entry["declared_path"])
            for entry in companion_artifacts
            if entry["required"] is True and entry["status"] == "missing"
        ]
        return {
            "primary_artifact": str(primary_artifact),
            "companion_artifacts": companion_artifacts,
            "missing_required": missing_required,
            "staged_file_count": sum(int(entry["file_count"]) for entry in companion_artifacts),
            "verification_result": "failed" if missing_required else "passed",
        }

    @staticmethod
    def _companion_manifest(ext: dict[str, str]) -> list[dict[str, Any]]:
        raw_manifest = ext.get("melix.companion_manifest", "").strip()
        if not raw_manifest:
            return []
        try:
            payload = json.loads(raw_manifest)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        declarations: list[dict[str, Any]] = []
        for raw_entry in payload:
            if not isinstance(raw_entry, dict):
                continue
            declared_path = str(raw_entry.get("path", "")).strip()
            if not declared_path:
                continue
            kind = str(raw_entry.get("kind", "file")).strip().lower()
            if kind not in {"file", "directory"}:
                kind = "file"
            required_raw = str(raw_entry.get("required", "true")).strip().lower()
            declarations.append(
                {
                    "path": declared_path,
                    "kind": kind,
                    "required": required_raw not in {"0", "false", "no", "off"},
                }
            )
        return declarations

    @classmethod
    def _companion_artifact_receipt(
        cls,
        *,
        primary_artifact: Path,
        companion_search_artifact: Path,
        ext: dict[str, str],
        declaration: dict[str, Any],
        stage: bool = False,
    ) -> dict[str, Any]:
        declared_path = str(declaration["path"])
        kind = str(declaration["kind"])
        required = bool(declaration["required"])
        resolved_path = cls._resolve_companion_path(
            declared_path=declared_path,
            primary_artifact=primary_artifact,
            companion_search_artifact=companion_search_artifact,
            ext=ext,
        )
        status = "missing"
        file_count = 0
        byte_count = 0
        files: list[str] = []
        if resolved_path is not None:
            if kind == "directory" and resolved_path.is_dir():
                if stage:
                    resolved_path = cls._stage_companion_path(
                        declared_path=declared_path,
                        source_path=resolved_path,
                        primary_artifact=primary_artifact,
                    )
                file_paths = sorted(path for path in resolved_path.rglob("*") if path.is_file())
                files = [str(path) for path in file_paths]
                file_count = len(file_paths)
                byte_count = sum(path.stat().st_size for path in file_paths)
                status = "present"
            elif kind == "file" and resolved_path.is_file():
                if stage:
                    resolved_path = cls._stage_companion_path(
                        declared_path=declared_path,
                        source_path=resolved_path,
                        primary_artifact=primary_artifact,
                    )
                files = [str(resolved_path)]
                file_count = 1
                byte_count = resolved_path.stat().st_size
                status = "present"
            else:
                resolved_path = None
        return {
            "declared_path": declared_path,
            "resolved_path": str(resolved_path) if resolved_path is not None else "",
            "kind": kind,
            "required": required,
            "status": status,
            "file_count": file_count,
            "byte_count": byte_count,
            "files": files,
        }

    @staticmethod
    def _resolve_companion_path(
        *,
        declared_path: str,
        primary_artifact: Path,
        companion_search_artifact: Path,
        ext: dict[str, str],
    ) -> Path | None:
        candidate = Path(declared_path).expanduser()
        if candidate.is_absolute() and candidate.exists():
            return candidate.resolve()
        search_roots = [companion_search_artifact.parent, primary_artifact.parent]
        managed_root = ext.get("melix.managed_root", "").strip()
        if managed_root:
            search_roots.append(Path(managed_root).expanduser())
        for root in search_roots:
            resolved_root = root.resolve()
            resolved = (resolved_root / candidate).resolve()
            try:
                resolved.relative_to(resolved_root)
            except ValueError:
                continue
            if resolved.exists():
                return resolved
        return None

    @staticmethod
    def _remove_existing_companion_target(target_path: Path) -> None:
        if not target_path.exists() and not target_path.is_symlink():
            return
        if target_path.is_dir() and not target_path.is_symlink():
            shutil.rmtree(target_path)
            return
        target_path.unlink()

    @classmethod
    def _stage_companion_path(
        cls,
        *,
        declared_path: str,
        source_path: Path,
        primary_artifact: Path,
    ) -> Path:
        target_path = primary_artifact.parent / Path(declared_path).name
        if source_path.resolve() == target_path.resolve():
            return target_path
        if source_path.is_dir():
            cls._remove_existing_companion_target(target_path)
            shutil.copytree(source_path, target_path)
            return target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        cls._remove_existing_companion_target(target_path)
        shutil.copy2(source_path, target_path)
        return target_path

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
    def _huggingface_token(ext: dict[str, Any]) -> str:
        for key in ("melix.hf_token", "hf_token", "HUGGINGFACE_HUB_TOKEN", "HF_TOKEN"):
            token = DownloadPipeline._ext_text(ext, key)
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
