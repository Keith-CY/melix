from __future__ import annotations

import array
import struct
import sys


def iter_samples(value):
    if isinstance(value, (float, int)):
        yield float(value)
        return
    flat_values = getattr(value, "flat", None)
    if flat_values is not None and not isinstance(value, (list, tuple)):
        for item in flat_values:
            yield float(item)
        return
    if hasattr(value, "tolist"):
        value = value.tolist()
    for item in value:
        if (
            isinstance(item, (list, tuple))
            or hasattr(item, "flat")
            or hasattr(item, "tolist")
        ):
            yield from iter_samples(item)
        else:
            yield float(item)


def pcm_sample_bytes(sample: float) -> int:
    clamped = max(-1.0, min(1.0, float(sample)))
    return int(clamped * 32767.0)


def audio_to_pcm_chunks(audio, *, chunk_sample_limit: int):
    chunk = array.array("h")
    limit = max(1, int(chunk_sample_limit))

    for sample in iter_samples(audio):
        chunk.append(pcm_sample_bytes(sample))
        if len(chunk) >= limit:
            if sys.byteorder != "little":
                chunk.byteswap()
            yield chunk.tobytes()
            chunk = array.array("h")
    if chunk:
        if sys.byteorder != "little":
            chunk.byteswap()
        yield chunk.tobytes()


def progressive_wav_header(
    sample_rate: int,
    *,
    channel_count: int = 1,
    bits_per_sample: int = 16,
) -> bytes:
    byte_rate = int(sample_rate) * int(channel_count) * int(bits_per_sample) // 8
    block_align = int(channel_count) * int(bits_per_sample) // 8
    return (
        b"RIFF"
        + struct.pack("<I", 0xFFFFFFFF)
        + b"WAVE"
        + b"fmt "
        + struct.pack(
            "<IHHIIHH",
            16,
            1,
            int(channel_count),
            int(sample_rate),
            byte_rate,
            block_align,
            int(bits_per_sample),
        )
        + b"data"
        + struct.pack("<I", 0xFFFFFFFF)
    )


def stream_chunk_sample_limit(sample_rate: int, stream_interval_ms: int) -> int:
    interval_ms = max(1, int(stream_interval_ms))
    return max(1, int(int(sample_rate) * interval_ms / 1000))
