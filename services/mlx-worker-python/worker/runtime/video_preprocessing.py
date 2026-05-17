from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
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


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
class ParsedVideoReference:
    raw: str
    scheme: str
    authority: str
    decoded_path: str
    path_name: str
    path_suffix: str


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
    parsed_reference = _parse_video_reference(uri)
    _validate_parsed_video_uri(parsed_reference)
    format_candidates: tuple[str | ParsedVideoReference, ...] = (
        (filename, parsed_reference) if filename else (parsed_reference,)
    )
    resolved_format = _resolve_video_format(format_name, mime_type, *format_candidates)
    resolved_filename = (
        filename or _filename_from_reference(parsed_reference) or f"remote-video.{resolved_format}"
    )
    byte_length = int(getattr(media, "byte_length", 0) or 0)
    return PreparedVideoInput(
        source_kind="uri",
        reference=uri,
        bytes_data=b"",
        mime_type=mime_type,
        format=resolved_format,
        filename=resolved_filename,
        byte_length=byte_length,
        duration_ms=duration_ms,
        frame_budget=frame_budget,
        start_ms=start_ms,
        end_ms=end_ms,
        sha256_hex=_uri_identity_hash(
            uri=uri,
            mime_type=mime_type,
            format_name=resolved_format,
            filename=resolved_filename,
            byte_length=byte_length,
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


def _parse_video_reference(reference: str) -> ParsedVideoReference:
    parsed = urlparse(reference)
    if parsed.scheme in {"http", "https", "file"}:
        parsed_path = parsed.path
        decoded_path = parsed_path if "%" not in parsed_path else unquote(parsed_path)
        path_name, path_suffix = _path_name_and_suffix(decoded_path)
    else:
        decoded_path = reference
        path_name, path_suffix = _path_name_and_suffix(reference)
    return ParsedVideoReference(
        raw=reference,
        scheme=parsed.scheme,
        authority=parsed.netloc,
        decoded_path=decoded_path,
        path_name=path_name,
        path_suffix=path_suffix,
    )


def _path_name_and_suffix(path: str) -> tuple[str, str]:
    path_name = path.rstrip("/").rsplit("/", 1)[-1]
    dot_index = path_name.rfind(".")
    path_suffix = path_name[dot_index + 1 :].lower() if 0 < dot_index < len(path_name) - 1 else ""
    return path_name, path_suffix


def _validate_video_uri(reference: str | ParsedVideoReference) -> None:
    parsed_reference = (
        reference if isinstance(reference, ParsedVideoReference) else _parse_video_reference(reference)
    )
    _validate_parsed_video_uri(parsed_reference)


def _validate_parsed_video_uri(reference: ParsedVideoReference) -> None:
    scheme = reference.scheme
    if scheme in {"", "file"}:
        return
    if scheme == "https":
        _validate_remote_video_reference(reference)
        return
    raise VideoPreprocessError(f"Unsupported video URI scheme: {scheme}.")


def _validate_remote_video_reference(reference: ParsedVideoReference) -> None:
    authority = reference.authority
    if not authority:
        raise VideoPreprocessError("Remote video URI requires a host.")
    first_character = authority[0]
    if (
        first_character != "["
        and not first_character.isdigit()
        and "@" not in authority
        and ":" not in authority
        and "l" not in authority
        and "L" not in authority
    ):
        return
    authority = authority.rsplit("@", 1)[-1].strip()
    if not authority:
        raise VideoPreprocessError("Remote video URI requires a host.")
    first_character = authority[0]
    if first_character != "[" and not first_character.isdigit() and ":" not in authority:
        if not _authority_may_be_localhost(authority):
            return
        authority_lower = authority.lower()
    else:
        authority_lower = authority.lower()
    host = _host_from_authority(authority_lower)
    if not host:
        raise VideoPreprocessError("Remote video URI requires a host.")
    if host == "localhost" or host.endswith(".localhost"):
        raise VideoPreprocessError(f"Remote video URI host is not allowed: {host}.")
    if not _looks_like_ip_literal(host):
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_private or address.is_loopback or address.is_link_local:
        raise VideoPreprocessError(f"Remote video URI host is not allowed: {host}.")


def _authority_may_be_localhost(authority: str) -> bool:
    if len(authority) < len("localhost"):
        return False
    if authority[0] not in {"l", "L", "."} and ".l" not in authority and ".L" not in authority:
        return False
    return _authority_mentions_localhost(authority.lower())


def _authority_mentions_localhost(authority: str) -> bool:
    return (
        authority == "localhost"
        or authority.startswith("localhost:")
        or authority.endswith(".localhost")
        or ".localhost:" in authority
    )


def _host_from_authority(authority: str) -> str:
    if authority.startswith("["):
        end_index = authority.find("]")
        return authority[1:end_index] if end_index > 1 else ""
    return authority.split(":", 1)[0]


def _looks_like_ip_literal(host: str) -> bool:
    return ":" in host or host[0].isdigit()


def _resolve_video_format(
    format_name: str,
    mime_type: str,
    *candidates: str | ParsedVideoReference,
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


def _infer_format(candidate: str | ParsedVideoReference) -> str:
    parsed_reference = (
        candidate if isinstance(candidate, ParsedVideoReference) else _parse_video_reference(candidate.strip())
    )
    if not parsed_reference.raw:
        return ""
    suffix = parsed_reference.path_suffix
    return suffix if suffix in SUPPORTED_VIDEO_FORMATS else ""


def _filename_from_reference(reference: str | ParsedVideoReference) -> str:
    parsed_reference = (
        reference if isinstance(reference, ParsedVideoReference) else _parse_video_reference(reference)
    )
    return parsed_reference.path_name


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
    framed_payload = (
        f"{uri}\0{mime_type}\0{format_name}\0{filename}\0"
        f"{byte_length}\0{duration_ms}\0{frame_budget}\0{start_ms}\0{end_ms}\0"
    )
    return hashlib.sha256(framed_payload.encode("utf-8")).hexdigest()


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
