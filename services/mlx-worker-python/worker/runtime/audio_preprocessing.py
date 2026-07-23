from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import unquote, urlparse


class AudioPreprocessError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedAudioInput:
    bytes_data: bytes
    local_path: str
    source_kind: str
    reference: str
    mime_type: str
    format: str
    filename: str
    chunk_count: int
    duration_seconds: float
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int

    def decoded_text(self) -> str:
        return self.bytes_data.decode("utf-8", errors="replace").strip()


def prepare_audio_input(request, *, read_uri_bytes: bool = True) -> PreparedAudioInput:
    started_at = perf_counter()
    media = getattr(request, "audio", None)
    mime_type = getattr(media, "mime_type", "")
    format_name = request.format or getattr(media, "format", "")
    filename = getattr(media, "filename", "")
    input_bytes: int | None = None

    if request.audio_bytes:
        bytes_data = bytes(request.audio_bytes)
        local_path = ""
        source_kind = "inline"
        reference = "inline:audio"
    elif request.audio_uri:
        try:
            if read_uri_bytes:
                path = _path_from_uri(request.audio_uri)
                local_path = os.fspath(path)
                bytes_data = path.read_bytes()
            else:
                local_path = _local_path_from_uri(request.audio_uri)
                bytes_data = b""
                input_bytes = os.stat(local_path).st_size
        except OSError as exc:
            raise AudioPreprocessError(f"Missing local audio input: {request.audio_uri}") from exc
        source_kind = "uri"
        reference = request.audio_uri
        if not format_name:
            format_name = _suffix_format_from_path(local_path)
        if not filename:
            filename = _basename_from_path(local_path)
    else:
        raise AudioPreprocessError("No audio input provided.")

    if input_bytes is None:
        input_bytes = len(bytes_data)
    chunk_count = max(1, (input_bytes + 7) // 8)
    duration_seconds = max(0.001, round(input_bytes / 16000.0, 6))
    latency_ms = max(0.0, (perf_counter() - started_at) * 1000.0)
    return PreparedAudioInput(
        bytes_data=bytes_data,
        local_path=local_path,
        source_kind=source_kind,
        reference=reference,
        mime_type=mime_type,
        format=format_name or "wav",
        filename=filename or "inline-audio",
        chunk_count=chunk_count,
        duration_seconds=duration_seconds,
        preprocess_latency_ms=latency_ms,
        preprocess_input_bytes=input_bytes,
        preprocess_peak_memory_bytes=input_bytes,
    )


def _suffix_format_from_path(local_path: str) -> str:
    dot_index = local_path.rfind(".")
    if dot_index < 0 or dot_index == len(local_path) - 1:
        return ""
    slash_index = local_path.rfind(os.sep)
    if dot_index <= slash_index + 1:
        return ""
    return local_path[dot_index + 1 :]


def _basename_from_path(local_path: str) -> str:
    slash_index = local_path.rfind(os.sep)
    if slash_index < 0:
        return local_path
    return local_path[slash_index + 1 :]


def _path_from_uri(uri: str) -> Path:
    return Path(_local_path_from_uri(uri))


def _local_path_from_uri(uri: str) -> str:
    if uri.startswith("file:///"):
        path_part = uri[7:]
        return path_part if "%" not in path_part else unquote(path_part)
    if uri.startswith("file://"):
        path_part = uri[7:]
        if path_part.startswith("localhost/"):
            path_part = path_part[len("localhost") :]
        elif not path_part.startswith("/"):
            parsed = urlparse(uri)
            path_part = parsed.path
        return path_part if "%" not in path_part else unquote(path_part)
    if "://" not in uri:
        return uri
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise AudioPreprocessError(f"Unsupported audio URI scheme: {parsed.scheme}")
    parsed_path = parsed.path
    return parsed_path if "%" not in parsed_path else unquote(parsed_path)
