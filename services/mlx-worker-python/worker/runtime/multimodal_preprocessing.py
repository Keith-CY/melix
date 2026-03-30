from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from urllib.parse import unquote, urlparse


class MultimodalPreprocessError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedImageInput:
    bytes_data: bytes
    source_kind: str
    reference: str
    mime_type: str
    format: str
    filename: str
    sha256_hex: str

    @property
    def byte_length(self) -> int:
        return len(self.bytes_data)

    def decoded_text(self) -> str:
        return self.bytes_data.decode("utf-8", errors="replace").strip()


@dataclass(frozen=True)
class PreparedVisionRequest:
    prompt_text: str
    images: list[PreparedImageInput]
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int
    prompt_hash_hex: str = ""
    multimodal_hash_hex: str = ""


def prepare_vision_request(messages) -> PreparedVisionRequest:
    started_at = perf_counter()
    prompt_segments: list[str] = []
    images: list[PreparedImageInput] = []
    input_bytes = 0

    for message in messages:
        for part in message.parts:
            if part.text:
                text = str(part.text).strip()
                if text:
                    prompt_segments.append(text)
            if part.image_bytes or part.image_uri:
                image = _prepare_image_part(part)
                images.append(image)
                input_bytes += image.byte_length

    if not images:
        raise MultimodalPreprocessError("No image input provided.")

    prompt_text = "\n".join(prompt_segments).strip()
    latency_ms = max(0.0, (perf_counter() - started_at) * 1000.0)
    prompt_hash_hex = _sha256_hex(prompt_text.encode("utf-8"))
    multimodal_hash_hex = _vision_request_hash(prompt_hash_hex, images)
    return PreparedVisionRequest(
        prompt_text=prompt_text,
        images=images,
        preprocess_latency_ms=latency_ms,
        preprocess_input_bytes=input_bytes,
        preprocess_peak_memory_bytes=input_bytes,
        prompt_hash_hex=prompt_hash_hex,
        multimodal_hash_hex=multimodal_hash_hex,
    )


def _prepare_image_part(part) -> PreparedImageInput:
    media = getattr(part, "media", None)
    mime_type = getattr(media, "mime_type", "")
    format_name = getattr(media, "format", "")
    filename = getattr(media, "filename", "")

    if part.image_bytes:
        bytes_data = bytes(part.image_bytes)
        return PreparedImageInput(
            bytes_data=bytes_data,
            source_kind="inline",
            reference="inline:image",
            mime_type=mime_type,
            format=format_name,
            filename=filename or "inline-image",
            sha256_hex=_sha256_hex(bytes_data),
        )

    if part.image_uri:
        path = _path_from_uri(part.image_uri)
        bytes_data = path.read_bytes()
        return PreparedImageInput(
            bytes_data=bytes_data,
            source_kind="uri",
            reference=part.image_uri,
            mime_type=mime_type,
            format=format_name or path.suffix.lstrip("."),
            filename=filename or path.name,
            sha256_hex=_sha256_hex(bytes_data),
        )

    raise MultimodalPreprocessError("No image input provided.")


def _path_from_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme in {"", "file"}:
        if parsed.scheme == "file":
            candidate = Path(unquote(parsed.path))
        else:
            candidate = Path(uri)
        if not candidate.exists():
            raise MultimodalPreprocessError(f"Missing local image input: {uri}")
        return candidate
    raise MultimodalPreprocessError(f"Unsupported image URI scheme: {parsed.scheme}")


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _vision_request_hash(prompt_hash_hex: str, images: list[PreparedImageInput]) -> str:
    digest = hashlib.sha256()
    digest.update(prompt_hash_hex.encode("ascii"))
    for image in images:
        digest.update(image.sha256_hex.encode("ascii"))
    return digest.hexdigest()
