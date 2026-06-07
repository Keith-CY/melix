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


_SET_FROZEN_ATTR = object.__setattr__


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


class ResponseOnlyBoundary:
    """Per-sample response-only boundary record persisted in the manifest."""

    __slots__ = ("assistant_offset", "total_tokens")

    assistant_offset: int
    total_tokens: int

    def __init__(
        self,
        assistant_offset: int,
        total_tokens: int,
        _set_attr: Any = _SET_FROZEN_ATTR,
    ) -> None:
        _set_attr(self, "assistant_offset", assistant_offset)
        _set_attr(self, "total_tokens", total_tokens)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("cannot assign to field " + repr(name))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ResponseOnlyBoundary):
            return (
                self.assistant_offset == other.assistant_offset
                and self.total_tokens == other.total_tokens
            )
        return NotImplemented

    def __repr__(self) -> str:
        return (
            "ResponseOnlyBoundary(assistant_offset="
            f"{self.assistant_offset!r}, total_tokens={self.total_tokens!r})"
        )

    @property
    def response_tokens(self) -> int:
        return max(0, self.total_tokens - self.assistant_offset)

    def trainable_response_tokens(self, max_seq_length: int | None) -> int:
        """Return response tokens that survive MLX-LM's sequence truncation."""

        if max_seq_length is None or max_seq_length <= 0:
            effective_total = self.total_tokens
        else:
            effective_total = min(self.total_tokens, max_seq_length)
        return max(0, effective_total - self.assistant_offset)


@dataclass(frozen=True, slots=True)
class ResponseOnlyBoundaryAggregate:
    """Aggregate stats computed across a normalized-dataset pass."""

    sample_count: int
    boundary_min: int
    boundary_max: int
    boundary_mean: float
    response_tokens_min: int = 0
    response_tokens_max: int = 0
    response_tokens_mean: float = 0.0
    trainable_response_tokens_min: int = 0
    trainable_response_tokens_max: int = 0
    trainable_response_tokens_mean: float = 0.0
    trainable_response_token_count: int = 0
    truncated_response_sample_count: int = 0
    fully_truncated_response_sample_count: int = 0

    def to_manifest_fields(self) -> dict[str, Any]:
        return {
            "response_only_boundary_sample_count": self.sample_count,
            "response_only_boundary_min": self.boundary_min,
            "response_only_boundary_max": self.boundary_max,
            "response_only_boundary_mean": round(self.boundary_mean, 3),
            "response_only_response_tokens_min": self.response_tokens_min,
            "response_only_response_tokens_max": self.response_tokens_max,
            "response_only_response_tokens_mean": round(self.response_tokens_mean, 3),
            "response_only_trainable_response_tokens_min": self.trainable_response_tokens_min,
            "response_only_trainable_response_tokens_max": self.trainable_response_tokens_max,
            "response_only_trainable_response_tokens_mean": round(self.trainable_response_tokens_mean, 3),
            "response_only_trainable_response_token_count": self.trainable_response_token_count,
            "response_only_truncated_response_sample_count": self.truncated_response_sample_count,
            "response_only_fully_truncated_response_sample_count": self.fully_truncated_response_sample_count,
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
    *,
    max_seq_length: int | None = None,
) -> ResponseOnlyBoundaryAggregate:
    """Reduce per-sample boundaries into manifest-ready aggregate stats.

    Single-pass implementation: accepts any iterable (including a generator
    over a multi-thousand-sample dataset) and only keeps running totals, never
    materializing an intermediate list of offsets.
    """

    sample_count = 0
    boundary_min = 0
    boundary_max = 0
    response_tokens_min = 0
    response_tokens_max = 0
    trainable_response_tokens_min = 0
    trainable_response_tokens_max = 0
    total_offset = 0
    total_response_tokens = 0
    total_trainable_response_tokens = 0
    truncated_response_sample_count = 0
    fully_truncated_response_sample_count = 0
    has_truncation_limit = max_seq_length is not None and max_seq_length > 0
    if has_truncation_limit:
        effective_limit = max_seq_length
        for entry in boundaries:
            offset = entry.assistant_offset
            total_tokens = entry.total_tokens
            response_tokens = total_tokens - offset
            if response_tokens < 0:
                response_tokens = 0
            if total_tokens > effective_limit:
                total_tokens = effective_limit
            trainable_response_tokens = total_tokens - offset
            if trainable_response_tokens < 0:
                trainable_response_tokens = 0
            if sample_count == 0:
                boundary_min = offset
                boundary_max = offset
                response_tokens_min = response_tokens
                response_tokens_max = response_tokens
                trainable_response_tokens_min = trainable_response_tokens
                trainable_response_tokens_max = trainable_response_tokens
            else:
                if offset < boundary_min:
                    boundary_min = offset
                if offset > boundary_max:
                    boundary_max = offset
                if response_tokens < response_tokens_min:
                    response_tokens_min = response_tokens
                if response_tokens > response_tokens_max:
                    response_tokens_max = response_tokens
                if trainable_response_tokens < trainable_response_tokens_min:
                    trainable_response_tokens_min = trainable_response_tokens
                if trainable_response_tokens > trainable_response_tokens_max:
                    trainable_response_tokens_max = trainable_response_tokens
            total_offset += offset
            total_response_tokens += response_tokens
            total_trainable_response_tokens += trainable_response_tokens
            if trainable_response_tokens < response_tokens:
                truncated_response_sample_count += 1
            if response_tokens > 0 and trainable_response_tokens == 0:
                fully_truncated_response_sample_count += 1
            sample_count += 1
    else:
        iterator = iter(boundaries)
        for entry in iterator:
            offset = entry.assistant_offset
            total_tokens = entry.total_tokens
            response_tokens = total_tokens - offset
            if response_tokens < 0:
                response_tokens = 0
            sample_count = 1
            boundary_min = offset
            boundary_max = offset
            response_tokens_min = response_tokens
            response_tokens_max = response_tokens
            total_offset = offset
            total_response_tokens = response_tokens
            break
        for entry in iterator:
            offset = entry.assistant_offset
            total_tokens = entry.total_tokens
            response_tokens = total_tokens - offset
            if response_tokens < 0:
                response_tokens = 0
            if offset < boundary_min:
                boundary_min = offset
            if offset > boundary_max:
                boundary_max = offset
            if response_tokens < response_tokens_min:
                response_tokens_min = response_tokens
            if response_tokens > response_tokens_max:
                response_tokens_max = response_tokens
            total_offset += offset
            total_response_tokens += response_tokens
            sample_count += 1
        trainable_response_tokens_min = response_tokens_min
        trainable_response_tokens_max = response_tokens_max
        total_trainable_response_tokens = total_response_tokens
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
        response_tokens_min=response_tokens_min,
        response_tokens_max=response_tokens_max,
        response_tokens_mean=total_response_tokens / sample_count,
        trainable_response_tokens_min=trainable_response_tokens_min,
        trainable_response_tokens_max=trainable_response_tokens_max,
        trainable_response_tokens_mean=total_trainable_response_tokens / sample_count,
        trainable_response_token_count=total_trainable_response_tokens,
        truncated_response_sample_count=truncated_response_sample_count,
        fully_truncated_response_sample_count=fully_truncated_response_sample_count,
    )
