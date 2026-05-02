from __future__ import annotations

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
        if self._is_managed_hub_repo_import(ext):
            return self._run_managed_hub_repo_import(
                request=request,
                job_id=job_id,
                output_dir=output_dir,
                ext=ext,
            )

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
        public_ext = self._public_ext(request.ext)
        config_payload = self._load_model_config_payload(runtime_model_path)
        draft_metadata = dflash_draft_metadata(config_payload)
        payload = {
            "schema_version": "melix.download_job.v1",
            "job_id": job_id,
            "operation": "download",
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
        while stack:
            current = pop_directory()
            with scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        append_directory(entry.path)
                        continue
                    if entry.is_file(follow_symlinks=False):
                        total_bytes += entry.stat(follow_symlinks=False).st_size
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
            "ext": self._public_ext(request.ext),
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
