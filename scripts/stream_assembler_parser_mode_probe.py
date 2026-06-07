from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.stream_assembler import RequestStreamAssembler, StreamFragment


def _build_chunks(chunk_count: int) -> tuple[list[str], int]:
    chunks: list[str] = []
    raw = ""
    harmony_channel_count = 0
    for index in range(chunk_count):
        if index % 120 == 0:
            piece = (
                '<think>plan</think>'
                '<tool_call>{"id":"call-%d","name":"search","arguments":{"q":"alpha"}}</tool_call>'
            ) % index
        elif index % 90 == 45:
            channel = "analysis" if (index // 90) % 2 == 0 else "final"
            piece = f"<|channel>{channel} metadata\n<channel|>channel-{index} "
            harmony_channel_count += 1
        elif index % 17 == 0:
            piece = "alpha<tool_ca"
        else:
            piece = f" token-{index} "
        raw += piece
        chunks.append(raw)
    return chunks, harmony_channel_count


def main() -> int:
    chunk_count = int(os.environ.get("MELIX_STREAM_ASSEMBLER_PARSER_MODE_CHUNKS", "1200"))
    sample_count = int(os.environ.get("MELIX_STREAM_ASSEMBLER_PARSER_MODE_SAMPLES", "64"))
    chunks, harmony_channel_count = _build_chunks(chunk_count)

    elapsed: list[float] = []
    tool_counts: list[int] = []
    channel_name_calls: list[int] = []
    channel_name_checksums: list[int] = []
    original_pipe_channel_name = RequestStreamAssembler._pipe_channel_name
    for _ in range(sample_count):
        pipe_channel_calls = 0
        pipe_channel_checksum = 0

        def tracked_pipe_channel_name(header: str) -> str:
            nonlocal pipe_channel_calls, pipe_channel_checksum
            pipe_channel_calls += 1
            name = original_pipe_channel_name(header)
            pipe_channel_checksum += len(name)
            return name

        RequestStreamAssembler._pipe_channel_name = staticmethod(tracked_pipe_channel_name)
        try:
            assembler = RequestStreamAssembler("probe", True, "", "qwen")
            started = time.perf_counter()
            tool_count = 0
            for chunk in chunks:
                tool_count += sum(
                    1
                    for delta in assembler.accept(StreamFragment(raw_text=chunk))
                    if delta.tool_call is not None
                )
            completed = assembler.completed()
        finally:
            RequestStreamAssembler._pipe_channel_name = staticmethod(original_pipe_channel_name)
        elapsed.append((time.perf_counter() - started) * 1000.0)
        tool_counts.append(tool_count)
        channel_name_calls.append(pipe_channel_calls)
        channel_name_checksums.append(pipe_channel_checksum)
        if completed.metrics["tool_call_markup_leak_count"] != 0:
            raise SystemExit("tool markup leaked")

    expected_tool_calls = sum(1 for index in range(chunk_count) if index % 120 == 0)
    if len(set(tool_counts)) != 1 or tool_counts[0] != expected_tool_calls:
        raise SystemExit(f"unexpected tool counts: {tool_counts!r}")
    if len(set(channel_name_calls)) != 1 or channel_name_calls[0] != harmony_channel_count:
        raise SystemExit(f"unexpected channel-name calls: {channel_name_calls!r}")
    if len(set(channel_name_checksums)) != 1 or channel_name_checksums[0] <= 0:
        raise SystemExit(f"unexpected channel-name checksums: {channel_name_checksums!r}")

    print(
        json.dumps(
            {
                "elapsed_ms_mean": statistics.fmean(elapsed),
                "raw_char_count": float(len(chunks[-1]) if chunks else 0),
                "tool_call_count": float(tool_counts[0]),
                "harmony_channel_count": float(harmony_channel_count),
                "channel_name_calls_mean": statistics.fmean(channel_name_calls),
                "channel_name_checksum": float(channel_name_checksums[0]),
                "sample_count": float(sample_count),
                "chunk_count": float(chunk_count),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
