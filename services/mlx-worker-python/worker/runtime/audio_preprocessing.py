from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path
from time import perf_counter
from urllib.parse import unquote, urlparse


class AudioPreprocessError(ValueError):
    pass


@dataclass(frozen=True)
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
        path = _path_from_uri(request.audio_uri)
        if read_uri_bytes:
            bytes_data = path.read_bytes()
        else:
            bytes_data = b""
            input_bytes = path.stat().st_size
        local_path = str(path)
        source_kind = "uri"
        reference = request.audio_uri
        if not format_name:
            format_name = path.suffix.lstrip(".")
        if not filename:
            filename = path.name
    else:
        raise AudioPreprocessError("No audio input provided.")

    if input_bytes is None:
        input_bytes = len(bytes_data)
    chunk_count = max(1, ceil(input_bytes / 8))
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


def _path_from_uri(uri: str) -> Path:
    if uri.startswith("file://"):
        path_part = uri[7:]
        if path_part.startswith("localhost/"):
            path_part = path_part[len("localhost") :]
        elif not path_part.startswith("/"):
            parsed = urlparse(uri)
            path_part = parsed.path
        candidate = Path(unquote(path_part))
    elif "://" not in uri:
        candidate = Path(uri)
    else:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise AudioPreprocessError(f"Unsupported audio URI scheme: {parsed.scheme}")
        candidate = Path(unquote(parsed.path))
    if not candidate.exists():
        raise AudioPreprocessError(f"Missing local audio input: {uri}")
    return candidate
