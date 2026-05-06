#!/usr/bin/env python3
"""Synthetic probe for training-dataset chunker top-level copy reuse."""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.model_ops.training_dataset_chunker import chunk_long_samples


class _ProbeTokenizer:
    def __init__(self, *, overhead_per_message: int = 5) -> None:
        self.overhead_per_message = overhead_per_message

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        add_generation_prompt: bool = False,
        return_dict: bool = False,
    ) -> list[int]:
        total = 0
        for message in messages:
            content = message.get("content", "") or ""
            total += self.overhead_per_message + len(content.split())
        if tools:
            total += len(tools) * 3
        if add_generation_prompt:
            total += self.overhead_per_message
        return list(range(total))


def _words(count: int) -> str:
    return " ".join(f"w{index}" for index in range(count))


def _build_sample(*, top_level_key_count: int, word_count: int) -> dict[str, object]:
    sample: dict[str, object] = {
        "id": "chunker-probe",
        "messages": [
            {"role": "user", "content": _words(word_count)},
            {"role": "assistant", "content": "ack"},
        ],
        "tools": [{"type": "function", "function": {"name": "lookup"}}],
    }
    for index in range(top_level_key_count):
        sample[f"metadata_{index:03d}"] = {
            "rank": index,
            "labels": [f"label-{index}", f"bucket-{index % 11}"],
        }
    return sample


def main() -> int:
    sample_count = int(os.environ.get("MELIX_CHUNKER_PROBE_SAMPLES", "7"))
    top_level_key_count = int(os.environ.get("MELIX_CHUNKER_PROBE_TOP_KEYS", "120"))
    word_count = int(os.environ.get("MELIX_CHUNKER_PROBE_WORDS", "8000"))
    chunk_size = int(os.environ.get("MELIX_CHUNKER_PROBE_CHUNK_SIZE", "60"))

    tokenizer = _ProbeTokenizer()
    elapsed_samples: list[float] = []
    peak_samples: list[float] = []
    chunk_counts: list[int] = []

    for _ in range(sample_count):
        sample = _build_sample(
            top_level_key_count=top_level_key_count,
            word_count=word_count,
        )
        tracemalloc.start()
        started = time.perf_counter()
        chunked, stats = chunk_long_samples([sample], chunk_size=chunk_size, tokenizer=tokenizer)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_samples.append(float(peak))
        if stats.chunk_count != len(chunked) or stats.chunk_count <= 1:
            raise RuntimeError("chunker probe did not produce multiple valid chunks")
        if any(chunk.get("tools") is not sample["tools"] for chunk in chunked):
            raise RuntimeError("chunker probe lost shared top-level tools payload")
        chunk_counts.append(stats.chunk_count)

    metrics = {
        "elapsed_ms_mean": round(statistics.fmean(elapsed_samples), 6),
        "peak_bytes_mean": round(statistics.fmean(peak_samples), 3),
        "chunk_count": float(chunk_counts[0]),
        "top_level_key_count": float(top_level_key_count + 3),
        "sample_count": float(sample_count),
    }
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
