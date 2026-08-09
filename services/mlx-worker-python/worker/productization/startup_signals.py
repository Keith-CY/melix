from __future__ import annotations

import json
import socket
from builtins import open as _OPEN
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Mapping, NamedTuple


PORT_CONFLICT_PATTERNS = (
    "address already in use",
    "eaddrinuse",
    "bind() failed",
    "port is already in use",
)
CRASH_PATTERNS = (
    "fatal error",
    "traceback",
    "uncaught",
    "assertion failed",
    "terminated",
    "abort trap",
)
_BYTE_WHITESPACE = bytes(value for value in range(256) if chr(value).isspace())
_ASCII_WHITESPACE_FLAGS = tuple(chr(value).isspace() for value in range(128))
_ORD = ord
_VERSION_KEY = b"version"
_VERSION_CANONICAL_PREFIX = b'version = "'
_QUOTE_BYTE = 34
_EQUALS_BYTE = 61
_PRODUCT_VERSION_CACHE: dict[str, tuple[int, int, str]] = {}
_PRODUCT_VERSION_PATH_CACHE: dict[str, Path] = {}
_PRODUCT_VERSION_CACHE_KEY_CACHE: dict[str, str] = {}
_UPDATE_CHANNEL_CACHE: dict[str, tuple[int, int, str, str]] = {}


class UpdateCheckResult(NamedTuple):
    checked: bool
    update_available: bool
    installed_version: str
    latest_version: str
    channel: str
    summary: str
    detail: str


_UPDATE_CHECK_RESULT_CACHE: dict[tuple[str, str, str, str], UpdateCheckResult] = {}
_UPDATE_CHECK_RESULT_STAT_CACHE: dict[tuple[str, str], tuple[int, int, UpdateCheckResult]] = {}


@dataclass(frozen=True, slots=True)
class StartupFailureReport:
    classification: str
    summary: str
    detail: str
    http_port: int
    ready_probe_url: str
    primary_log_path: str
    log_excerpt: str

    def to_dict(self) -> dict[str, object]:
        return {
            "classification": self.classification,
            "summary": self.summary,
            "detail": self.detail,
            "http_port": self.http_port,
            "ready_probe_url": self.ready_probe_url,
            "primary_log_path": self.primary_log_path,
            "log_excerpt": self.log_excerpt,
        }


def read_product_version(repo_root: str | Path) -> str:
    root = (
        repo_root
        if isinstance(repo_root, Path) and repo_root.is_absolute()
        else Path(repo_root).expanduser().resolve()
    )
    root_text = str(root)
    pyproject_path = _PRODUCT_VERSION_PATH_CACHE.get(root_text)
    if pyproject_path is None:
        pyproject_path = root / "pyproject.toml"
        _PRODUCT_VERSION_PATH_CACHE[root_text] = pyproject_path
        cache_key = str(pyproject_path)
        _PRODUCT_VERSION_CACHE_KEY_CACHE[root_text] = cache_key
    else:
        cache_key = _PRODUCT_VERSION_CACHE_KEY_CACHE.get(root_text)
        if cache_key is None:
            cache_key = str(pyproject_path)
            _PRODUCT_VERSION_CACHE_KEY_CACHE[root_text] = cache_key
    stat_result = pyproject_path.stat()
    cached = _PRODUCT_VERSION_CACHE.get(cache_key)
    if cached is not None:
        cached_mtime_ns, cached_size, cached_version = cached
        if cached_mtime_ns == stat_result.st_mtime_ns and cached_size == stat_result.st_size:
            return cached_version
    with pyproject_path.open("rb") as handle:
        for raw_line in handle:
            if not raw_line.startswith(_VERSION_KEY):
                continue
            if raw_line.startswith(_VERSION_CANONICAL_PREFIX) and raw_line.endswith(b'"\n'):
                version = raw_line[len(_VERSION_CANONICAL_PREFIX) : -2].decode("utf-8")
                _PRODUCT_VERSION_CACHE[cache_key] = (
                    stat_result.st_mtime_ns,
                    stat_result.st_size,
                    version,
                )
                return version
            version = _version_from_pyproject_line(raw_line)
            if version is not None:
                _PRODUCT_VERSION_CACHE[cache_key] = (
                    stat_result.st_mtime_ns,
                    stat_result.st_size,
                    version,
                )
                return version
    raise ValueError(f"Unable to read version from {pyproject_path}")


def _version_from_pyproject_line(raw_line: bytes) -> str | None:
    key_length = len(_VERSION_KEY)
    cursor = key_length
    line_length = len(raw_line)
    while cursor < line_length and raw_line[cursor] in _BYTE_WHITESPACE:
        cursor += 1
    if cursor >= line_length or raw_line[cursor] != _EQUALS_BYTE:
        return None
    cursor += 1
    while cursor < line_length and raw_line[cursor] in _BYTE_WHITESPACE:
        cursor += 1
    if cursor >= line_length or raw_line[cursor] != _QUOTE_BYTE:
        return None
    value_start = cursor + 1
    value_end = raw_line.find(b'"', value_start)
    if value_end < 0:
        return None
    cursor = value_end + 1
    while cursor < line_length and raw_line[cursor] in _BYTE_WHITESPACE:
        cursor += 1
    if cursor != line_length:
        return None
    return raw_line[value_start:value_end].decode("utf-8")


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
    resolved_channel_path = (
        channel_path
        if isinstance(channel_path, Path) and channel_path.is_absolute()
        else Path(channel_path).expanduser().resolve()
    )
    stat_result = resolved_channel_path.stat()
    stat_mtime_ns = stat_result.st_mtime_ns
    stat_size = stat_result.st_size
    channel_path_text = str(resolved_channel_path)
    stat_cache_key = (channel_path_text, installed_version)
    stat_cached = _UPDATE_CHECK_RESULT_STAT_CACHE.get(stat_cache_key)
    if stat_cached is not None:
        cached_mtime_ns, cached_size, cached_result = stat_cached
        if cached_mtime_ns == stat_mtime_ns and cached_size == stat_size:
            return cached_result
    latest_version, channel = _read_update_channel_version(
        resolved_channel_path,
        stat_mtime_ns=stat_mtime_ns,
        stat_size=stat_size,
        cache_key=channel_path_text,
    )
    cache_key = (channel_path_text, installed_version, latest_version, channel)
    if latest_version:
        comparison = compare_versions(latest_version, installed_version)
        if comparison > 0:
            result = UpdateCheckResult(
                checked=True,
                update_available=True,
                installed_version=installed_version,
                latest_version=latest_version,
                channel=channel,
                summary=f"Update available: {latest_version}",
                detail=f"Current {installed_version} on {channel}",
            )
            _UPDATE_CHECK_RESULT_CACHE[cache_key] = result
            _UPDATE_CHECK_RESULT_STAT_CACHE[stat_cache_key] = (
                stat_mtime_ns,
                stat_size,
                result,
            )
            return result
        result = UpdateCheckResult(
            checked=True,
            update_available=False,
            installed_version=installed_version,
            latest_version=latest_version,
            channel=channel,
            summary="Update: up to date",
            detail=f"Current {installed_version} on {channel}",
        )
        _UPDATE_CHECK_RESULT_CACHE[cache_key] = result
        _UPDATE_CHECK_RESULT_STAT_CACHE[stat_cache_key] = (
            stat_mtime_ns,
            stat_size,
            result,
        )
        return result
    result = UpdateCheckResult(
        checked=False,
        update_available=False,
        installed_version=installed_version,
        latest_version="",
        channel=channel,
        summary="Update check failed",
        detail=f"Channel metadata at {resolved_channel_path} does not declare latest_version",
    )
    _UPDATE_CHECK_RESULT_CACHE[cache_key] = result
    _UPDATE_CHECK_RESULT_STAT_CACHE[stat_cache_key] = (
        stat_mtime_ns,
        stat_size,
        result,
    )
    return result


def _read_update_channel_version(
    channel_path: Path,
    *,
    stat_mtime_ns: int,
    stat_size: int,
    cache_key: str,
) -> tuple[str, str]:
    cached = _UPDATE_CHANNEL_CACHE.get(cache_key)
    if cached is not None:
        cached_mtime_ns, cached_size, cached_latest_version, cached_channel = cached
        if cached_mtime_ns == stat_mtime_ns and cached_size == stat_size:
            return cached_latest_version, cached_channel
    payload = json.loads(channel_path.read_bytes())
    latest_version = str(payload.get("latest_version", "")).strip()
    channel = str(payload.get("channel", "stable")).strip() or "stable"
    _UPDATE_CHANNEL_CACHE[cache_key] = (
        stat_mtime_ns,
        stat_size,
        latest_version,
        channel,
    )
    return latest_version, channel


@lru_cache(maxsize=16_384)
def compare_versions(left: str, right: str) -> int:
    if left == right:
        return 0
    ord_ = _ORD
    ascii_whitespace_flags = _ASCII_WHITESPACE_FLAGS
    left_length = len(left)
    right_length = len(right)
    if left and right:
        left_start_code = ord_(left[0])
        right_start_code = ord_(right[0])
        if left_length == right_length + 1 and left_start_code == 118 and left.startswith(right, 1):
            return 0
        if right_length == left_length + 1 and right_start_code == 118 and right.startswith(left, 1):
            return 0
        left_end_code = ord_(left[-1])
        right_end_code = ord_(right[-1])
        left_boundary_clean = (
            left_start_code < 128
            and left_end_code < 128
            and not ascii_whitespace_flags[left_start_code]
            and not ascii_whitespace_flags[left_end_code]
        ) or (
            left_start_code >= 128
            and left_end_code >= 128
            and not left[0].isspace()
            and not left[-1].isspace()
        )
        right_boundary_clean = (
            right_start_code < 128
            and right_end_code < 128
            and not ascii_whitespace_flags[right_start_code]
            and not ascii_whitespace_flags[right_end_code]
        ) or (
            right_start_code >= 128
            and right_end_code >= 128
            and not right[0].isspace()
            and not right[-1].isspace()
        )
        if left_boundary_clean and right_boundary_clean:
            left_index = 1 if left[0] == "v" else 0
            right_index = 1 if right[0] == "v" else 0
            return _compare_normalized_version_parts(left, right, left_index, right_index)

    left_cleaned = left.strip()
    right_cleaned = right.strip()
    if left_cleaned == right_cleaned:
        return 0
    left_index = 1 if left_cleaned and left_cleaned[0] == "v" else 0
    right_index = 1 if right_cleaned and right_cleaned[0] == "v" else 0
    if left_index != right_index:
        left_length = len(left_cleaned)
        right_length = len(right_cleaned)
        if left_index and left_length == right_length + 1 and left_cleaned.startswith(right_cleaned, 1):
            return 0
        if right_index and right_length == left_length + 1 and right_cleaned.startswith(left_cleaned, 1):
            return 0
    return _compare_normalized_version_parts(
        left_cleaned,
        right_cleaned,
        left_index,
        right_index,
    )


def normalized_version_parts(value: str) -> list[int]:
    value_length = len(value)
    index = 0
    while index < value_length and value[index].isspace():
        index += 1
    end = value_length
    while end > index and value[end - 1].isspace():
        end -= 1
    if index < end and value[index] == "v":
        index += 1

    parts: list[int] = []
    current_value = 0
    digit_seen = False
    digit_prefix_active = True
    part_has_chars = False
    ord_ = _ORD

    while index < end:
        character_code = ord_(value[index])
        index += 1
        if character_code == 43 or character_code == 45:
            break
        if character_code == 46:
            if part_has_chars:
                parts.append(current_value if digit_seen else 0)
            current_value = 0
            digit_seen = False
            digit_prefix_active = True
            part_has_chars = False
            continue
        part_has_chars = True
        if digit_prefix_active and 48 <= character_code <= 57:
            current_value = current_value * 10 + (character_code - 48)
            digit_seen = True
        else:
            digit_prefix_active = False

    if part_has_chars:
        parts.append(current_value if digit_seen else 0)
    return parts or [0]


def _compare_normalized_version_parts(
    left: str,
    right: str,
    left_index: int,
    right_index: int,
) -> int:
    left_length = len(left)
    right_length = len(right)
    ord_ = _ORD

    while True:
        left_value = 0
        left_digit_seen = False
        left_digit_prefix_active = True
        left_part_has_chars = False
        while left_index < left_length:
            character_code = ord_(left[left_index])
            left_index += 1
            if character_code == 43 or character_code == 45:
                left_index = left_length
                break
            if character_code == 46:
                if left_part_has_chars:
                    break
                continue
            left_part_has_chars = True
            if left_digit_prefix_active and 48 <= character_code <= 57:
                left_value = left_value * 10 + (character_code - 48)
                left_digit_seen = True
            else:
                left_digit_prefix_active = False
        left_done = not left_part_has_chars
        if not left_digit_seen:
            left_value = 0

        right_value = 0
        right_digit_seen = False
        right_digit_prefix_active = True
        right_part_has_chars = False
        while right_index < right_length:
            character_code = ord_(right[right_index])
            right_index += 1
            if character_code == 43 or character_code == 45:
                right_index = right_length
                break
            if character_code == 46:
                if right_part_has_chars:
                    break
                continue
            right_part_has_chars = True
            if right_digit_prefix_active and 48 <= character_code <= 57:
                right_value = right_value * 10 + (character_code - 48)
                right_digit_seen = True
            else:
                right_digit_prefix_active = False
        right_done = not right_part_has_chars
        if not right_digit_seen:
            right_value = 0

        if left_done and right_done:
            return 0
        if left_value < right_value:
            return -1
        if left_value > right_value:
            return 1
        if left_index >= left_length and right_index >= right_length:
            return 0


def _next_normalized_version_part(value: str, index: int) -> tuple[int, int, bool]:
    current_value = 0
    digit_seen = False
    digit_prefix_active = True
    part_has_chars = False
    value_length = len(value)

    while index < value_length:
        character_code = _ORD(value[index])
        index += 1
        if character_code == 43 or character_code == 45:
            index = value_length
            break
        if character_code == 46:
            if part_has_chars:
                return current_value if digit_seen else 0, index, False
            continue
        part_has_chars = True
        if digit_prefix_active and 48 <= character_code <= 57:
            current_value = current_value * 10 + (character_code - 48)
            digit_seen = True
        else:
            digit_prefix_active = False

    if part_has_chars:
        return current_value if digit_seen else 0, index, False
    return 0, index, True


def _iter_normalized_version_parts(value: str) -> Iterator[int]:
    cleaned = value.strip()
    start_index = 1 if cleaned.startswith("v") else 0
    current_value = 0
    digit_seen = False
    digit_prefix_active = True
    part_has_chars = False

    for character in cleaned[start_index:]:
        character_code = _ORD(character)
        if character_code == 43 or character_code == 45:
            break
        if character_code == 46:
            if part_has_chars:
                yield current_value if digit_seen else 0
            current_value = 0
            digit_seen = False
            digit_prefix_active = True
            part_has_chars = False
            continue
        part_has_chars = True
        if digit_prefix_active and 48 <= character_code <= 57:
            current_value = current_value * 10 + (character_code - 48)
            digit_seen = True
        else:
            digit_prefix_active = False

    if part_has_chars:
        yield current_value if digit_seen else 0


def classify_startup_failure(
    manifest: Mapping[str, Any],
    *,
    error_text: str = "",
) -> StartupFailureReport:
    ready_probe_url = str(manifest.get("ready_probe_url", ""))
    http_port = int(manifest.get("http_port", 0) or 0)
    primary_log_path = str(manifest.get("control_plane_stderr_path", ""))
    summary = ""
    detail = ""
    excerpt = ""

    if error_text:
        error_lower = error_text.lower()
        if _contains_any(error_lower, PORT_CONFLICT_PATTERNS):
            summary = f"Configured HTTP port {http_port} is already in use."
            detail = (
                f"The control plane could not bind to {ready_probe_url}. "
                f"Choose a different host port or stop the conflicting process."
            )
            excerpt = error_text
            classification = "host_port_conflict"
        elif _contains_any(error_lower, CRASH_PATTERNS):
            summary = "Control plane crashed before startup completed."
            detail = f"Melix never reached {ready_probe_url}. Inspect the control-plane logs for the crash cause."
            excerpt = error_text
            classification = "control_plane_crash"
        else:
            classification = ""
    else:
        classification = ""

    if not classification:
        control_plane_stderr_path = manifest.get("control_plane_stderr_path")
        control_plane_stdout_path = manifest.get("control_plane_stdout_path")
        python_worker_stderr_path = manifest.get("python_worker_stderr_path")
        swift_text_worker_stderr_path = manifest.get("swift_text_worker_stderr_path")
        python_worker_stdout_path = manifest.get("python_worker_stdout_path")
        swift_text_worker_stdout_path = manifest.get("swift_text_worker_stdout_path")

        if not (
            control_plane_stderr_path
            or control_plane_stdout_path
            or python_worker_stderr_path
            or swift_text_worker_stderr_path
            or python_worker_stdout_path
            or swift_text_worker_stdout_path
        ):
            return StartupFailureReport(
                classification="startup_hang",
                summary=f"Melix startup timed out before {ready_probe_url} became ready.",
                detail="Inspect the startup logs and ready probe path to determine whether the services hung or never launched.",
                http_port=http_port,
                ready_probe_url=ready_probe_url,
                primary_log_path=primary_log_path,
                log_excerpt=error_text,
            )

        control_plane_excerpt = _log_excerpt(
            control_plane_stderr_path,
            control_plane_stdout_path,
        )

        if control_plane_excerpt:
            control_plane_lower = control_plane_excerpt.lower()
            control_plane_port_conflict = _contains_any(
                control_plane_lower, PORT_CONFLICT_PATTERNS
            )
            control_plane_crash = not control_plane_port_conflict and _contains_any(
                control_plane_lower, CRASH_PATTERNS
            )
        else:
            control_plane_port_conflict = False
            control_plane_crash = False

        if control_plane_port_conflict:
            summary = f"Configured HTTP port {http_port} is already in use."
            detail = (
                f"The control plane could not bind to {ready_probe_url}. "
                f"Choose a different host port or stop the conflicting process."
            )
            excerpt = control_plane_excerpt
            classification = "host_port_conflict"
        elif control_plane_crash:
            summary = "Control plane crashed before startup completed."
            detail = f"Melix never reached {ready_probe_url}. Inspect the control-plane logs for the crash cause."
            excerpt = control_plane_excerpt
            classification = "control_plane_crash"
        else:
            worker_excerpt_value = _log_excerpt(
                python_worker_stderr_path,
                swift_text_worker_stderr_path,
                python_worker_stdout_path,
                swift_text_worker_stdout_path,
            )
            worker_crash = bool(worker_excerpt_value) and _contains_any(
                worker_excerpt_value.lower(), CRASH_PATTERNS
            )
            if worker_crash:
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


def _contains_any(value: str, patterns: tuple[str, ...]) -> bool:
    if not value:
        return False
    if patterns is PORT_CONFLICT_PATTERNS:
        return (
            "address already in use" in value
            or "eaddrinuse" in value
            or "bind() failed" in value
            or "port is already in use" in value
        )
    if patterns is CRASH_PATTERNS:
        return (
            "fatal error" in value
            or "traceback" in value
            or "uncaught" in value
            or "assertion failed" in value
            or "terminated" in value
            or "abort trap" in value
        )
    for pattern in patterns:
        if pattern in value:
            return True
    return False


def _log_excerpt(*paths: object) -> str:
    combined_excerpt = ""
    for path in paths:
        if not path:
            continue
        path_text = str(path)
        resolved = path_text if path_text[:1] != "~" else Path(path_text).expanduser()
        try:
            excerpt = _read_last_nonempty_line(resolved)
        except OSError:
            continue
        if not excerpt:
            continue
        if not combined_excerpt:
            combined_excerpt = excerpt
        else:
            combined_excerpt = f"{combined_excerpt} | {excerpt}"
    return combined_excerpt


def _read_last_nonempty_line(path: str | Path, *, chunk_size: int = 8192) -> str:
    with _OPEN(path, "rb") as handle:
        handle.seek(0, 2)
        line_start, payload_end = _seek_last_nonempty_line_bounds(handle, chunk_size=chunk_size)
        if payload_end == 0:
            return ""
        handle.seek(line_start)
        payload = handle.read(payload_end - line_start)
    return payload.decode("utf-8", errors="replace")


def _right_stripped_chunk_length(chunk: bytes) -> int:
    return 0 if chunk.isspace() else len(chunk.rstrip(_BYTE_WHITESPACE))


def _seek_last_nonempty_line_bounds(handle: Any, *, chunk_size: int) -> tuple[int, int]:
    position = handle.tell()
    payload_end = 0
    while position > 0:
        read_size = min(chunk_size, position)
        start = position - read_size
        handle.seek(start)
        chunk = handle.read(read_size)
        if payload_end == 0:
            search_end = _right_stripped_chunk_length(chunk)
            if search_end == 0:
                position = start
                continue
            payload_end = start + search_end
        else:
            search_end = len(chunk)
        newline_index = chunk.rfind(b"\n", 0, search_end)
        if newline_index < 0:
            newline_index = chunk.rfind(b"\r", 0, search_end)
        if newline_index >= 0:
            return start + newline_index + 1, payload_end
        position = start
    return 0, payload_end
