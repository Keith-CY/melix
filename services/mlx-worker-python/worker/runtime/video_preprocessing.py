from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from urllib.parse import unquote, urlparse


class VideoPreprocessError(ValueError):
    pass


SUPPORTED_VIDEO_FORMATS = {"mp4", "mov", "m4v", "webm"}
SUPPORTED_VIDEO_MIME_TYPES = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-m4v": "m4v",
    "video/webm": "webm",
}
MAX_VIDEO_FRAME_BUDGET = 128


@dataclass(frozen=True)
class PreparedVideoInput:
    source_kind: str
    reference: str
    bytes_data: bytes
    mime_type: str
    format: str
    filename: str
    byte_length: int
    duration_ms: int
    frame_budget: int
    start_ms: int
    end_ms: int
    sha256_hex: str


def prepare_video_input(part) -> PreparedVideoInput:
    media = getattr(part, "media", None)
    mime_type = str(getattr(media, "mime_type", "") or "").strip().lower()
    format_name = str(getattr(media, "format", "") or "").strip().lower()
    filename = str(getattr(media, "filename", "") or "").strip()
    duration_ms = int(getattr(media, "duration_ms", 0) or 0)
    frame_budget = int(getattr(media, "frame_budget", 0) or 0)
    start_ms = int(getattr(media, "start_ms", 0) or 0)
    end_ms = int(getattr(media, "end_ms", 0) or 0)

    _validate_bounds(duration_ms, frame_budget, start_ms, end_ms)

    if part.video_bytes:
        bytes_data = bytes(part.video_bytes)
        resolved_format = _resolve_video_format(format_name, mime_type, filename)
        return PreparedVideoInput(
            source_kind="inline",
            reference="inline:video",
            bytes_data=bytes_data,
            mime_type=mime_type,
            format=resolved_format,
            filename=filename or f"inline-video.{resolved_format}",
            byte_length=len(bytes_data),
            duration_ms=duration_ms,
            frame_budget=frame_budget,
            start_ms=start_ms,
            end_ms=end_ms,
            sha256_hex=_sha256_hex(bytes_data),
        )

    uri = str(getattr(part, "video_uri", "") or "").strip()
    if not uri:
        raise VideoPreprocessError("No video input provided.")
    _validate_video_uri(uri)
    resolved_format = _resolve_video_format(format_name, mime_type, filename, uri)
    resolved_filename = filename or _filename_from_reference(uri) or f"remote-video.{resolved_format}"
    return PreparedVideoInput(
        source_kind="uri",
        reference=uri,
        bytes_data=b"",
        mime_type=mime_type,
        format=resolved_format,
        filename=resolved_filename,
        byte_length=int(getattr(media, "byte_length", 0) or 0),
        duration_ms=duration_ms,
        frame_budget=frame_budget,
        start_ms=start_ms,
        end_ms=end_ms,
        sha256_hex=_uri_identity_hash(
            uri=uri,
            mime_type=mime_type,
            format_name=resolved_format,
            filename=resolved_filename,
            byte_length=int(getattr(media, "byte_length", 0) or 0),
            duration_ms=duration_ms,
            frame_budget=frame_budget,
            start_ms=start_ms,
            end_ms=end_ms,
        ),
    )


def _validate_bounds(duration_ms: int, frame_budget: int, start_ms: int, end_ms: int) -> None:
    if duration_ms < 0:
        raise VideoPreprocessError("duration_ms must be greater than or equal to 0.")
    if frame_budget < 0:
        raise VideoPreprocessError("frame_budget must be greater than or equal to 0.")
    if frame_budget > MAX_VIDEO_FRAME_BUDGET:
        raise VideoPreprocessError(
            f"frame_budget must be less than or equal to {MAX_VIDEO_FRAME_BUDGET}."
        )
    if start_ms < 0:
        raise VideoPreprocessError("start_ms must be greater than or equal to 0.")
    if end_ms < 0:
        raise VideoPreprocessError("end_ms must be greater than or equal to 0.")
    if end_ms and start_ms > end_ms:
        raise VideoPreprocessError("end_ms must be greater than or equal to start_ms.")
    if duration_ms and end_ms and end_ms > duration_ms:
        raise VideoPreprocessError("end_ms must be less than or equal to duration_ms.")


def _validate_video_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme in {"", "file", "http", "https"}:
        return
    raise VideoPreprocessError(f"Unsupported video URI scheme: {parsed.scheme}.")


def _resolve_video_format(
    format_name: str,
    mime_type: str,
    *candidates: str,
) -> str:
    if format_name:
        if format_name in SUPPORTED_VIDEO_FORMATS:
            return format_name
        raise VideoPreprocessError(f"Unsupported video format: {format_name}.")
    if mime_type:
        resolved = SUPPORTED_VIDEO_MIME_TYPES.get(mime_type)
        if resolved:
            return resolved
        raise VideoPreprocessError(f"Unsupported video format: {mime_type}.")
    for candidate in candidates:
        inferred = _infer_format(candidate)
        if inferred:
            return inferred
    raise VideoPreprocessError("input_video.format or input_video.mime_type is required.")


def _infer_format(candidate: str) -> str:
    trimmed = candidate.strip()
    if not trimmed:
        return ""
    parsed = urlparse(trimmed)
    if parsed.scheme in {"http", "https", "file"}:
        suffix = Path(unquote(parsed.path)).suffix.lstrip(".").lower()
    else:
        suffix = Path(trimmed).suffix.lstrip(".").lower()
    return suffix if suffix in SUPPORTED_VIDEO_FORMATS else ""


def _filename_from_reference(reference: str) -> str:
    parsed = urlparse(reference)
    if parsed.scheme in {"http", "https", "file"}:
        return Path(unquote(parsed.path)).name
    return Path(reference).name


def _uri_identity_hash(
    *,
    uri: str,
    mime_type: str,
    format_name: str,
    filename: str,
    byte_length: int,
    duration_ms: int,
    frame_budget: int,
    start_ms: int,
    end_ms: int,
) -> str:
    digest = hashlib.sha256()
    for value in (
        uri,
        mime_type,
        format_name,
        filename,
        str(byte_length),
        str(duration_ms),
        str(frame_budget),
        str(start_ms),
        str(end_ms),
    ):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
