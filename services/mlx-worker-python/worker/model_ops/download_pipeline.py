from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.protocol.python.worker.v1 import maintenance_pb2

from worker.model_ops.errors import ModelOperationError
from worker.model_registry.dflash_metadata import dflash_draft_metadata


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
        managed_root = ext.get("melix.managed_root", "").strip() or os.environ.get("MELIX_MANAGED_MODEL_ROOT", "").strip()
        if not managed_root:
            raise ModelOperationError(
                code="invalid_argument",
                message="managed hub import requires MELIX_MANAGED_MODEL_ROOT.",
            )

        source_dir = self._resolve_managed_hub_source_path(output_dir=output_dir, ext=ext, repo_id=repo_id, revision=revision)
        materialized_dir = self._materialize_managed_hub_repo(
            source_dir=source_dir,
            managed_root=Path(managed_root),
            repo_id=repo_id,
            revision=revision,
            ext=ext,
        )
        total_bytes = self._directory_size(materialized_dir)
        state_path = output_dir / "download.state.json"
        manifest_json = self._build_managed_import_manifest_json(
            request=request,
            job_id=job_id,
            output_dir=output_dir,
            output_path=materialized_dir,
            state_path=state_path,
            repo_id=repo_id,
            revision=revision,
            total_bytes=total_bytes,
        )
        return DownloadPipelineResult(
            output_path=materialized_dir,
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

        cache_dir = output_dir / "hf-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        downloaded = snapshot_download(
            repo_id=repo_id,
            revision=revision,
            local_dir_use_symlinks=False,
            cache_dir=os.fspath(cache_dir),
        )
        return Path(downloaded).resolve()

    def _materialize_managed_hub_repo(
        self,
        *,
        source_dir: Path,
        managed_root: Path,
        repo_id: str,
        revision: str,
        ext: dict[str, str],
    ) -> Path:
        organization_id, model_name = repo_id.split("/", maxsplit=1)
        materialized_dir = managed_root / "huggingface" / organization_id / model_name / revision
        materialized_dir.parent.mkdir(parents=True, exist_ok=True)
        if materialized_dir.exists():
            shutil.rmtree(materialized_dir)
        shutil.copytree(source_dir, materialized_dir)
        manifest_path = materialized_dir / "manifest.json"
        manifest_payload = self._managed_registry_manifest_payload(
            repo_id=repo_id,
            revision=revision,
            model_path=materialized_dir,
            ext=ext,
        )
        manifest_path.write_text(json.dumps(manifest_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return materialized_dir

    @staticmethod
    def _managed_registry_manifest_payload(
        *,
        repo_id: str,
        revision: str,
        model_path: Path,
        ext: dict[str, str],
    ) -> dict[str, Any]:
        organization_id, model_name = repo_id.split("/", maxsplit=1)
        model_kind = ext.get("melix.model_kind", "").strip() or "text"
        max_context = DownloadPipeline._int(ext.get("melix.max_context"), default=0)
        parser_mode = ext.get("melix.parser_mode", "").strip() or "text"
        reasoning_mode = ext.get("melix.reasoning_mode", "").strip() or "off"
        tokenizer_hash = ext.get("melix.tokenizer_hash", "").strip() or f"hf.{repo_id.replace('/', '.')}"
        quant_profile_id = ext.get("melix.quant_profile_id", "").strip()
        capability_tasks = ext.get("melix.capability.supported_tasks", "").strip() or (
            "vlm,generate" if model_kind == "vlm" else "generate"
        )
        capability_modalities = ext.get("melix.capability.supported_modalities", "").strip() or (
            "text,image" if model_kind == "vlm" else "text"
        )
        config_payload = DownloadPipeline._load_model_config_payload(model_path)
        draft_metadata = dflash_draft_metadata(config_payload)
        return {
            "schema_version": "melix.model_registry_manifest.v1",
            "model_id": repo_id,
            "model_kind": model_kind,
            "revision": revision,
            "tokenizer_hash": tokenizer_hash,
            "quant_profile_id": quant_profile_id,
            "parser_mode": parser_mode,
            "reasoning_mode": reasoning_mode,
            "max_context": max_context,
            "provider_id": "huggingface",
            "organization_id": organization_id,
            "model_name": model_name,
            "variant_id": revision,
            "ext": {
                "melix.source_kind": "hub_repo",
                "melix.source_locator": repo_id,
                "melix.hf_repo_id": repo_id,
                "melix.hf_revision": revision,
                "melix.managed_import": "true",
                "melix.model_path": str(model_path),
                "melix.capability.supported_tasks": capability_tasks,
                "melix.capability.supported_modalities": capability_modalities,
                **draft_metadata,
            },
        }

    def _build_managed_import_manifest_json(
        self,
        *,
        request: maintenance_pb2.ConvertModelRequest,
        job_id: str,
        output_dir: Path,
        output_path: Path,
        state_path: Path,
        repo_id: str,
        revision: str,
        total_bytes: int,
    ) -> str:
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
                **dict(request.ext),
                "melix.hf_repo_id": repo_id,
                "melix.hf_revision": revision,
                "melix.source_kind": "hub_repo",
                "melix.source_locator": repo_id,
                "melix.managed_import": "true",
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
        return sum(file_path.stat().st_size for file_path in path.rglob("*") if file_path.is_file())

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
