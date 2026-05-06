from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

from worker.runtime.video_preprocessing import PreparedVideoInput, prepare_video_input


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
class PreparedVideoFramePolicy:
    reference: str
    sampling_strategy: str
    requested_frame_budget: int
    effective_frame_count: int
    clip_start_ms: int
    clip_end_ms: int
    clip_duration_ms: int


@dataclass(frozen=True)
class PreparedVisionRequest:
    prompt_text: str
    images: list[PreparedImageInput]
    videos: list[PreparedVideoInput]
    video_frame_policies: list[PreparedVideoFramePolicy]
    preprocess_latency_ms: float
    preprocess_input_bytes: int
    preprocess_peak_memory_bytes: int
    prompt_hash_hex: str = ""
    multimodal_hash_hex: str = ""

    @property
    def contains_video(self) -> bool:
        return bool(self.videos)

    @property
    def effective_video_frame_count(self) -> int:
        return sum(policy.effective_frame_count for policy in self.video_frame_policies)

    @property
    def requested_video_frame_budget(self) -> int:
        return sum(policy.requested_frame_budget for policy in self.video_frame_policies)

    @property
    def effective_video_window_ms(self) -> int:
        return sum(policy.clip_duration_ms for policy in self.video_frame_policies)


def prepare_vision_request(messages) -> PreparedVisionRequest:
    started_at = perf_counter()
    prompt_segments: list[str] = []
    images: list[PreparedImageInput] = []
    videos: list[PreparedVideoInput] = []
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
            if part.video_bytes or part.video_uri:
                video = prepare_video_input(part)
                videos.append(video)
                input_bytes += video.byte_length

    if not images and not videos:
        raise MultimodalPreprocessError("No image or video input provided.")

    prompt_text = "\n".join(prompt_segments).strip()
    latency_ms = max(0.0, (perf_counter() - started_at) * 1000.0)
    prompt_hash_hex = _sha256_hex(prompt_text.encode("utf-8"))
    video_frame_policies = [_effective_video_frame_policy(video) for video in videos]
    multimodal_hash_hex = _vision_request_hash(
        prompt_hash_hex,
        images,
        videos,
        video_frame_policies,
    )
    return PreparedVisionRequest(
        prompt_text=prompt_text,
        images=images,
        videos=videos,
        video_frame_policies=video_frame_policies,
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
        bytes_data, reference, detected_mime_type, detected_format, detected_filename = _bytes_from_image_uri(part.image_uri)
        return PreparedImageInput(
            bytes_data=bytes_data,
            source_kind="uri",
            reference=reference,
            mime_type=mime_type or detected_mime_type,
            format=format_name or detected_format,
            filename=filename or detected_filename,
            sha256_hex=_sha256_hex(bytes_data),
        )

    raise MultimodalPreprocessError("No image input provided.")


def _path_from_parsed_uri(uri: str, parsed) -> Path:
    if parsed.scheme in {"", "file"}:
        if parsed.scheme == "file":
            candidate = Path(unquote(parsed.path))
        else:
            candidate = Path(uri)
        if not candidate.exists():
            raise MultimodalPreprocessError(f"Missing local image input: {uri}")
        return candidate
    raise MultimodalPreprocessError(f"Unsupported image URI scheme: {parsed.scheme}")


def _path_from_uri(uri: str) -> Path:
    return _path_from_parsed_uri(uri, urlparse(uri))


def _bytes_from_image_uri(uri: str) -> tuple[bytes, str, str, str, str]:
    parsed = urlparse(uri)
    if parsed.scheme in {"", "file"}:
        path = _path_from_parsed_uri(uri, parsed)
        return (
            path.read_bytes(),
            uri,
            "",
            path.suffix.lstrip("."),
            path.name,
        )
    if parsed.scheme in {"http", "https"}:
        return _fetch_remote_image(uri)
    raise MultimodalPreprocessError(f"Unsupported image URI scheme: {parsed.scheme}")


def _fetch_remote_image(uri: str) -> tuple[bytes, str, str, str, str]:
    parsed = urlparse(uri)
    try:
        with urlopen(uri, timeout=5.0) as response:
            bytes_data = response.read()
            mime_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise MultimodalPreprocessError(f"Remote image fetch failed: {uri}") from exc

    path = Path(unquote(parsed.path))
    format_name = path.suffix.lstrip(".")
    if not format_name and mime_type:
        guessed = mimetypes.guess_extension(mime_type)
        format_name = guessed.lstrip(".") if guessed else ""
    filename = path.name or "remote-image"
    return bytes_data, uri, mime_type or "", format_name, filename


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _vision_request_hash(
    prompt_hash_hex: str,
    images: list[PreparedImageInput],
    videos: list[PreparedVideoInput],
    video_frame_policies: list[PreparedVideoFramePolicy],
) -> str:
    digest = hashlib.sha256()
    digest.update(prompt_hash_hex.encode("ascii"))
    for image in images:
        digest.update(image.sha256_hex.encode("ascii"))
    for video, policy in zip(videos, video_frame_policies, strict=False):
        digest.update(video.sha256_hex.encode("ascii"))
        for value in (
            policy.reference,
            policy.sampling_strategy,
            str(policy.requested_frame_budget),
            str(policy.effective_frame_count),
            str(policy.clip_start_ms),
            str(policy.clip_end_ms),
            str(policy.clip_duration_ms),
        ):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def rebuild_multimodal_hash(prepared_request: PreparedVisionRequest, prompt_hash_hex: str) -> str:
    return _vision_request_hash(
        prompt_hash_hex,
        prepared_request.images,
        prepared_request.videos,
        prepared_request.video_frame_policies,
    )


def _effective_video_frame_policy(video: PreparedVideoInput) -> PreparedVideoFramePolicy:
    clip_start_ms = max(video.start_ms, 0)
    clip_end_ms = _effective_clip_end_ms(video)
    clip_duration_ms = max(0, clip_end_ms - clip_start_ms) if clip_end_ms > 0 else 0
    requested_frame_budget = max(video.frame_budget, 0)
    effective_frame_count = requested_frame_budget or _default_frame_count(clip_duration_ms)
    return PreparedVideoFramePolicy(
        reference=video.reference,
        sampling_strategy="uniform_sample",
        requested_frame_budget=requested_frame_budget,
        effective_frame_count=effective_frame_count,
        clip_start_ms=clip_start_ms,
        clip_end_ms=clip_end_ms,
        clip_duration_ms=clip_duration_ms,
    )


def _effective_clip_end_ms(video: PreparedVideoInput) -> int:
    if video.end_ms > 0:
        return video.end_ms
    if video.duration_ms > 0:
        return video.duration_ms
    return 0


def _default_frame_count(clip_duration_ms: int) -> int:
    if clip_duration_ms <= 0:
        return 8
    return min(16, max(4, ceil(clip_duration_ms / 4_000.0)))
