from __future__ import annotations

import json
import re
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


PORT_CONFLICT_PATTERNS = [
    "address already in use",
    "eaddrinuse",
    "bind() failed",
    "port is already in use",
]
CRASH_PATTERNS = [
    "fatal error",
    "traceback",
    "uncaught",
    "assertion failed",
    "terminated",
    "abort trap",
]
_BYTE_WHITESPACE = bytes(value for value in range(256) if chr(value).isspace())


@dataclass(frozen=True)
class UpdateCheckResult:
    checked: bool
    update_available: bool
    installed_version: str
    latest_version: str
    channel: str
    summary: str
    detail: str


@dataclass(frozen=True)
class StartupFailureReport:
    classification: str
    summary: str
    detail: str
    http_port: int
    ready_probe_url: str
    primary_log_path: str
    log_excerpt: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def read_product_version(repo_root: str | Path) -> str:
    root = Path(repo_root).expanduser().resolve()
    pyproject_path = root / "pyproject.toml"
    payload = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', payload, re.MULTILINE)
    if match is None:
        raise ValueError(f"Unable to read version from {pyproject_path}")
    return match.group(1)


def default_update_channel_path(repo_root: str | Path) -> Path:
    return Path(repo_root).expanduser().resolve() / "infra/packaging/update-channels/stable.json"


def resolve_http_port(
    requested_port: int,
    *,
    host: str = "127.0.0.1",
    prefer_available_http_port: bool = False,
    search_limit: int = 32,
) -> int:
    if prefer_available_http_port is False:
        return requested_port
    for candidate in range(requested_port, requested_port + max(1, search_limit)):
        if port_is_available(candidate, host=host):
            return candidate
    raise RuntimeError(f"Unable to find an available HTTP port near {requested_port}")


def port_is_available(port: int, *, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            handle.bind((host, port))
        except OSError:
            return False
    return True


def check_for_updates(installed_version: str, channel_path: str | Path) -> UpdateCheckResult:
    payload = json.loads(Path(channel_path).expanduser().resolve().read_text(encoding="utf-8"))
    latest_version = str(payload.get("latest_version", "")).strip()
    channel = str(payload.get("channel", "stable")).strip() or "stable"
    if latest_version:
        comparison = compare_versions(latest_version, installed_version)
        if comparison > 0:
            return UpdateCheckResult(
                checked=True,
                update_available=True,
                installed_version=installed_version,
                latest_version=latest_version,
                channel=channel,
                summary=f"Update available: {latest_version}",
                detail=f"Current {installed_version} on {channel}",
            )
        return UpdateCheckResult(
            checked=True,
            update_available=False,
            installed_version=installed_version,
            latest_version=latest_version,
            channel=channel,
            summary="Update: up to date",
            detail=f"Current {installed_version} on {channel}",
        )
    return UpdateCheckResult(
        checked=False,
        update_available=False,
        installed_version=installed_version,
        latest_version="",
        channel=channel,
        summary="Update check failed",
        detail=f"Channel metadata at {Path(channel_path).expanduser().resolve()} does not declare latest_version",
    )


def compare_versions(left: str, right: str) -> int:
    left_parts = normalized_version_parts(left)
    right_parts = normalized_version_parts(right)
    width = max(len(left_parts), len(right_parts))
    left_normalized = left_parts + [0] * (width - len(left_parts))
    right_normalized = right_parts + [0] * (width - len(right_parts))
    if left_normalized < right_normalized:
        return -1
    if left_normalized > right_normalized:
        return 1
    return 0


def normalized_version_parts(value: str) -> list[int]:
    cleaned = value.strip()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    cleaned = cleaned.split("+", 1)[0]
    cleaned = cleaned.split("-", 1)[0]
    parts = [segment for segment in cleaned.split(".") if segment]
    normalized: list[int] = []
    for part in parts:
        digits = re.match(r"(\d+)", part)
        normalized.append(int(digits.group(1)) if digits else 0)
    return normalized or [0]


def classify_startup_failure(
    manifest: Mapping[str, Any],
    *,
    error_text: str = "",
) -> StartupFailureReport:
    ready_probe_url = str(manifest.get("ready_probe_url", ""))
    http_port = int(manifest.get("http_port", 0) or 0)
    error_lower = error_text.lower()
    primary_log_path = str(manifest.get("control_plane_stderr_path", ""))

    if any(pattern in error_lower for pattern in PORT_CONFLICT_PATTERNS):
        summary = f"Configured HTTP port {http_port} is already in use."
        detail = (
            f"The control plane could not bind to {ready_probe_url}. "
            f"Choose a different host port or stop the conflicting process."
        )
        excerpt = error_text
        classification = "host_port_conflict"
    else:
        control_plane_excerpt = _log_excerpt(
            manifest.get("control_plane_stderr_path"),
            manifest.get("control_plane_stdout_path"),
        )
        combined_control_plane = f"{error_lower}\n{control_plane_excerpt.lower()}"

        if any(pattern in combined_control_plane for pattern in PORT_CONFLICT_PATTERNS):
            summary = f"Configured HTTP port {http_port} is already in use."
            detail = (
                f"The control plane could not bind to {ready_probe_url}. "
                f"Choose a different host port or stop the conflicting process."
            )
            excerpt = control_plane_excerpt
            classification = "host_port_conflict"
        elif control_plane_excerpt and any(pattern in combined_control_plane for pattern in CRASH_PATTERNS):
            summary = "Control plane crashed before startup completed."
            detail = f"Melix never reached {ready_probe_url}. Inspect the control-plane logs for the crash cause."
            excerpt = control_plane_excerpt
            classification = "control_plane_crash"
        else:
            worker_excerpt_value = _log_excerpt(
                manifest.get("python_worker_stderr_path"),
                manifest.get("swift_text_worker_stderr_path"),
                manifest.get("python_worker_stdout_path"),
                manifest.get("swift_text_worker_stdout_path"),
            )
            combined_worker = worker_excerpt_value.lower()
            if worker_excerpt_value and any(pattern in combined_worker for pattern in CRASH_PATTERNS):
                primary_log_path = str(
                    manifest.get("python_worker_stderr_path")
                    or manifest.get("swift_text_worker_stderr_path")
                    or ""
                )
                summary = "A worker crashed before Melix became ready."
                detail = "Inspect the worker logs and restart Melix after fixing the failing runtime."
                excerpt = worker_excerpt_value
                classification = "worker_crash"
            else:
                summary = f"Melix startup timed out before {ready_probe_url} became ready."
                detail = "Inspect the startup logs and ready probe path to determine whether the services hung or never launched."
                excerpt = control_plane_excerpt or worker_excerpt_value or error_text
                classification = "startup_hang"

    return StartupFailureReport(
        classification=classification,
        summary=summary,
        detail=detail,
        http_port=http_port,
        ready_probe_url=ready_probe_url,
        primary_log_path=primary_log_path,
        log_excerpt=excerpt,
    )


def _log_excerpt(*paths: object) -> str:
    excerpts: list[str] = []
    for path in paths:
        if not path:
            continue
        resolved = Path(str(path)).expanduser()
        try:
            excerpt = _read_last_nonempty_line(resolved)
        except OSError:
            continue
        if excerpt:
            excerpts.append(excerpt)
    return " | ".join(excerpts)


def _read_last_nonempty_line(path: Path, *, chunk_size: int = 8192) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        payload_end = _seek_non_whitespace_end(handle, chunk_size=chunk_size)
        if payload_end == 0:
            return ""
        line_start = _seek_last_line_start(handle, payload_end=payload_end, chunk_size=chunk_size)
        handle.seek(line_start)
        payload = handle.read(payload_end - line_start)
    return payload.decode("utf-8", errors="replace").rstrip()


def _seek_non_whitespace_end(handle: Any, *, chunk_size: int) -> int:
    position = handle.tell()
    while position > 0:
        read_size = min(chunk_size, position)
        start = position - read_size
        handle.seek(start)
        chunk = handle.read(read_size)
        trimmed = chunk.rstrip(_BYTE_WHITESPACE)
        if trimmed:
            return start + len(trimmed)
        position = start
    return 0


def _seek_last_line_start(handle: Any, *, payload_end: int, chunk_size: int) -> int:
    position = payload_end
    while position > 0:
        read_size = min(chunk_size, position)
        start = position - read_size
        handle.seek(start)
        chunk = handle.read(read_size)
        newline_index = max(chunk.rfind(b"\n"), chunk.rfind(b"\r"))
        if newline_index >= 0:
            return start + newline_index + 1
        position = start
    return 0
