"""Template-aware response-only boundary computation (milestone #43 Phase 2).

Melix delegates response-only loss masking to MLX-LM's ``ChatDataset.process()``
which renders the chat template and derives an accurate prompt-boundary offset
at every training step. This module surfaces the **same** boundary to Melix at
dataset-preparation time so the training manifest can document how much of each
sample is masked — without changing masking semantics.

The computation is intentionally a thin wrapper around
``tokenizer.apply_chat_template`` so it stays bit-exact with what MLX-LM
computes. ``tests/test_response_only_boundary.py`` pins that equality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol, runtime_checkable


@runtime_checkable
class _ChatTemplateTokenizer(Protocol):
    """Minimal tokenizer surface we depend on.

    ``apply_chat_template`` is the HuggingFace / MLX-LM contract. We invoke it
    with ``return_dict=False`` to get a plain ``list[int]`` of token ids — the
    same call shape MLX-LM's ``ChatDataset.process`` uses, which makes our
    offset bit-exact with theirs. Passing ``tokenize=True`` explicitly would
    return a ``BatchEncoding`` (dict) in modern transformers, which is NOT
    what MLX-LM consumes, so we intentionally do not.
    """

    def apply_chat_template(  # pragma: no cover - protocol typing only
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = ...,
        add_generation_prompt: bool = ...,
        return_dict: bool = ...,
    ) -> list[int]:
        ...


@dataclass(frozen=True)
class ResponseOnlyBoundary:
    """Per-sample response-only boundary record persisted in the manifest."""

    assistant_offset: int
    total_tokens: int

    @property
    def response_tokens(self) -> int:
        return max(0, self.total_tokens - self.assistant_offset)


@dataclass(frozen=True)
class ResponseOnlyBoundaryAggregate:
    """Aggregate stats computed across a normalized-dataset pass."""

    sample_count: int
    boundary_min: int
    boundary_max: int
    boundary_mean: float

    def to_manifest_fields(self) -> dict[str, Any]:
        return {
            "response_only_boundary_sample_count": self.sample_count,
            "response_only_boundary_min": self.boundary_min,
            "response_only_boundary_max": self.boundary_max,
            "response_only_boundary_mean": round(self.boundary_mean, 3),
        }


def compute_response_only_boundary(
    messages: list[dict[str, str]],
    tokenizer: _ChatTemplateTokenizer,
    *,
    tools: list[dict[str, Any]] | None = None,
) -> ResponseOnlyBoundary:
    """Return the prompt-boundary offset and total token count for a chat sample.

    Bit-exact mirror of MLX-LM's ``ChatDataset.process``
    (``mlx_lm/tuner/datasets.py``). Upstream logic:

    * ``tokens = apply_chat_template(messages, tools=tools, return_dict=False)``
    * ``add_generation_prompt = messages[-1]["role"] == "assistant"``
    * ``offset = len(apply_chat_template(messages[:-1], tools=tools,
      add_generation_prompt=add_generation_prompt, return_dict=False))``

    ``tools`` is forwarded so samples that carry tool schemas don't silently
    desynchronize from what MLX-LM masks at training time. ``tokenizer`` is the
    HuggingFace-style tokenizer already loaded for training; the caller is
    expected to pass the same instance MLX-LM will use so the template
    rendering is identical.
    """

    if not messages:
        raise ValueError("messages must be non-empty.")

    add_generation_prompt = messages[-1].get("role") == "assistant"

    full_tokens = tokenizer.apply_chat_template(
        messages,
        tools=tools,
        add_generation_prompt=False,
        return_dict=False,
    )
    prefix_tokens = tokenizer.apply_chat_template(
        messages[:-1],
        tools=tools,
        add_generation_prompt=add_generation_prompt,
        return_dict=False,
    )
    total = len(full_tokens)
    offset = len(prefix_tokens)
    return ResponseOnlyBoundary(assistant_offset=offset, total_tokens=total)


def aggregate_response_only_boundaries(
    boundaries: Iterable[ResponseOnlyBoundary],
) -> ResponseOnlyBoundaryAggregate:
    """Reduce per-sample boundaries into manifest-ready aggregate stats.

    Single-pass implementation: accepts any iterable (including a generator
    over a multi-thousand-sample dataset) and only keeps running totals, never
    materializing an intermediate list of offsets.
    """

    sample_count = 0
    boundary_min = 0
    boundary_max = 0
    total_offset = 0
    for entry in boundaries:
        offset = entry.assistant_offset
        if sample_count == 0:
            boundary_min = offset
            boundary_max = offset
        else:
            if offset < boundary_min:
                boundary_min = offset
            if offset > boundary_max:
                boundary_max = offset
        total_offset += offset
        sample_count += 1
    if sample_count == 0:
        return ResponseOnlyBoundaryAggregate(
            sample_count=0,
            boundary_min=0,
            boundary_max=0,
            boundary_mean=0.0,
        )
    return ResponseOnlyBoundaryAggregate(
        sample_count=sample_count,
        boundary_min=boundary_min,
        boundary_max=boundary_max,
        boundary_mean=total_offset / sample_count,
    )
