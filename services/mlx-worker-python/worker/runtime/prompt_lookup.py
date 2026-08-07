"""Prompt-lookup (n-gram) speculative decoding.

Prompt-lookup decoding drafts continuation tokens by matching the current
generation suffix against n-grams already present in the request context
(prompt plus tokens generated so far), then verifies the draft with a single
batched forward pass of the target model. Unlike draft-model speculative
decoding it needs no extra weights, and unlike native MTP it needs no
architecture support — the win comes entirely from workloads whose output
overlaps their input: RAG answers quoting retrieved passages, code edits
echoing surrounding code, summarization, and agent turns repeating tool
schemas.

Greedy identity
---------------
Verification accepts the longest draft prefix that matches the target model's
own greedy predictions, then emits one additional (bonus) token from the same
forward pass. Because every emitted token equals a prediction the target model
made, the accelerated token sequence is identical to plain greedy decoding.
Proposing zero draft tokens degenerates to exactly one forward per token — the
baseline path — so the same loop serves both modes and the hysteresis fallback
below costs nothing beyond a normal decode.

Index semantics
---------------
`PromptLookupIndex` maps each n-gram to its **earliest** end position
(first-occurrence-wins). Earliest wins for two reasons: it biases drafts toward
the grounded document/prompt rather than the model's own recent output, and it
makes "the only occurrence is the suffix I am matching right now" detectable
(the stored position equals the current context end), which is precisely the
case where no draft exists.

This module deliberately imports no MLX symbols. The target-model forward is
supplied as a `step_fn` callable, so the decode loop is exercised end to end in
tests with deterministic fakes, and the MLX-backed step lives at the runtime
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Sequence


# Acceleration-policy ext keys. Prompt lookup is opt-in and rides on
# AccelerationPolicy.ext, so enabling it needs no protocol change.
ENABLED_EXT_KEY = "melix.prompt_lookup.enabled"
MAX_NGRAM_EXT_KEY = "melix.prompt_lookup.max_ngram"
MIN_NGRAM_EXT_KEY = "melix.prompt_lookup.min_ngram"
MAX_DRAFT_TOKENS_EXT_KEY = "melix.prompt_lookup.max_draft_tokens"
MIN_ACCEPT_RATE_EXT_KEY = "melix.prompt_lookup.min_accept_rate"
WARMUP_CYCLES_EXT_KEY = "melix.prompt_lookup.warmup_cycles"
COOLDOWN_CYCLES_EXT_KEY = "melix.prompt_lookup.cooldown_cycles"

_DEFAULT_MAX_NGRAM = 8
_DEFAULT_MIN_NGRAM = 2
_DEFAULT_MAX_DRAFT_TOKENS = 8
# Below this accept rate the 1 + n_draft token verify forward costs more than
# the tokens it saves, so proposing pauses.
_DEFAULT_MIN_ACCEPT_RATE = 0.2
_DEFAULT_WARMUP_CYCLES = 8
_DEFAULT_COOLDOWN_CYCLES = 16

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _truthy(raw_value: Any) -> bool:
    return str(raw_value or "").strip().lower() in _TRUTHY


def _bounded_int(raw_value: Any, *, default: int, minimum: int, maximum: int) -> int:
    text = str(raw_value or "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _bounded_float(raw_value: Any, *, default: float, minimum: float, maximum: float) -> float:
    text = str(raw_value or "").strip()
    if not text:
        return default
    try:
        value = float(text)
    except (TypeError, ValueError):
        return default
    if value != value:  # NaN
        return default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class PromptLookupConfig:
    """Resolved prompt-lookup knobs.

    `max_ngram` / `min_ngram` bound the suffix lengths tried when matching, from
    longest (most specific, highest expected accept rate) down to shortest.
    """

    enabled: bool = False
    max_ngram: int = _DEFAULT_MAX_NGRAM
    min_ngram: int = _DEFAULT_MIN_NGRAM
    max_draft_tokens: int = _DEFAULT_MAX_DRAFT_TOKENS
    min_accept_rate: float = _DEFAULT_MIN_ACCEPT_RATE
    warmup_cycles: int = _DEFAULT_WARMUP_CYCLES
    cooldown_cycles: int = _DEFAULT_COOLDOWN_CYCLES

    def __post_init__(self) -> None:
        # Normalize on every construction path, not just from_ext, so a
        # directly-built config can never express min_ngram > max_ngram.
        max_ngram = max(1, self.max_ngram)
        object.__setattr__(self, "max_ngram", max_ngram)
        object.__setattr__(self, "min_ngram", max(1, min(self.min_ngram, max_ngram)))

    @classmethod
    def from_ext(cls, ext: Any) -> "PromptLookupConfig":
        """Resolve config from an acceleration/execution ext mapping.

        Unparseable or out-of-range values fall back to the default rather than
        failing the request: prompt lookup is a performance path, and a bad knob
        must never turn into a failed generation.
        """
        get = getattr(ext, "get", None)
        if not callable(get):
            return _DISABLED
        if not _truthy(get(ENABLED_EXT_KEY, "")):
            # Shared immutable instance: this is the per-request hot path for
            # every request that does not opt in, so it must not allocate.
            return _DISABLED
        max_ngram = _bounded_int(
            get(MAX_NGRAM_EXT_KEY, ""), default=_DEFAULT_MAX_NGRAM, minimum=1, maximum=64
        )
        min_ngram = _bounded_int(
            get(MIN_NGRAM_EXT_KEY, ""), default=_DEFAULT_MIN_NGRAM, minimum=1, maximum=64
        )
        if min_ngram > max_ngram:
            min_ngram = max_ngram
        return cls(
            enabled=True,
            max_ngram=max_ngram,
            min_ngram=min_ngram,
            max_draft_tokens=_bounded_int(
                get(MAX_DRAFT_TOKENS_EXT_KEY, ""),
                default=_DEFAULT_MAX_DRAFT_TOKENS,
                minimum=1,
                maximum=64,
            ),
            min_accept_rate=_bounded_float(
                get(MIN_ACCEPT_RATE_EXT_KEY, ""),
                default=_DEFAULT_MIN_ACCEPT_RATE,
                minimum=0.0,
                maximum=1.0,
            ),
            warmup_cycles=_bounded_int(
                get(WARMUP_CYCLES_EXT_KEY, ""),
                default=_DEFAULT_WARMUP_CYCLES,
                minimum=1,
                maximum=4096,
            ),
            cooldown_cycles=_bounded_int(
                get(COOLDOWN_CYCLES_EXT_KEY, ""),
                default=_DEFAULT_COOLDOWN_CYCLES,
                minimum=1,
                maximum=4096,
            ),
        )


_DISABLED = PromptLookupConfig()


@dataclass
class PromptLookupStats:
    """Per-request counters, projected onto the speculative receipt fields."""

    cycle_count: int = 0
    proposed_tokens: int = 0
    accepted_tokens: int = 0
    rejected_tokens: int = 0
    emitted_tokens: int = 0
    fallback_count: int = 0
    paused_cycle_count: int = 0

    @property
    def acceptance_rate(self) -> float:
        if self.proposed_tokens <= 0:
            return 0.0
        return self.accepted_tokens / self.proposed_tokens

    @property
    def rollback_rate(self) -> float:
        if self.proposed_tokens <= 0:
            return 0.0
        return self.rejected_tokens / self.proposed_tokens


class PromptLookupIndex:
    """Incremental n-gram → earliest end-position index over one request context.

    The index is append-only and keyed on exact token tuples, so it holds only
    as much state as the context it covers and never needs rebuilding as
    generation extends the context.
    """

    def __init__(self, *, max_ngram: int, min_ngram: int) -> None:
        self._max_ngram = max(1, max_ngram)
        self._min_ngram = max(1, min(min_ngram, self._max_ngram))
        self._tokens: list[int] = []
        self._first_end_by_ngram: dict[tuple[int, ...], int] = {}

    @property
    def tokens(self) -> list[int]:
        return self._tokens

    def __len__(self) -> int:
        return len(self._tokens)

    def extend(self, tokens: Sequence[int]) -> None:
        """Append tokens and index every n-gram that newly became complete."""
        if not tokens:
            return
        previous_length = len(self._tokens)
        self._tokens.extend(int(token) for token in tokens)
        current_length = len(self._tokens)
        first_end_by_ngram = self._first_end_by_ngram
        setdefault = first_end_by_ngram.setdefault
        token_list = self._tokens
        for size in range(self._min_ngram, self._max_ngram + 1):
            # An n-gram of this size ending at `end` is new when its last token
            # is one of the tokens just appended.
            first_end = max(size, previous_length + 1)
            for end in range(first_end, current_length + 1):
                setdefault(tuple(token_list[end - size : end]), end)

    def propose(self, max_draft_tokens: int) -> list[int]:
        """Draft the continuation of the longest suffix seen earlier in context.

        Tries suffixes from `max_ngram` down to `min_ngram` and returns the
        tokens that followed the first (earliest) prior occurrence. Returns an
        empty list when no suffix recurs — the caller then runs a plain
        single-token step.
        """
        if max_draft_tokens <= 0:
            return []
        token_list = self._tokens
        context_length = len(token_list)
        if context_length < self._min_ngram + 1:
            return []
        first_end_by_ngram = self._first_end_by_ngram
        upper = min(self._max_ngram, context_length - 1)
        for size in range(upper, self._min_ngram - 1, -1):
            match_end = first_end_by_ngram.get(tuple(token_list[context_length - size : context_length]))
            # `match_end == context_length` means the suffix's only occurrence is
            # the suffix itself, so there is nothing earlier to continue from.
            if match_end is None or match_end >= context_length:
                continue
            draft = token_list[match_end : match_end + max_draft_tokens]
            if draft:
                return list(draft)
        return []


@dataclass
class _HysteresisGate:
    """Pause proposing when drafts stop paying for their verify forward.

    Without this, an adversarial (no-overlap) workload would pay a
    `1 + max_draft_tokens` wide forward for every single emitted token. After
    `warmup_cycles` observed cycles the gate compares the observed accept rate
    against the floor and, if it is below, pauses drafting for
    `cooldown_cycles` cycles before probing again.
    """

    config: PromptLookupConfig
    _cooldown_remaining: int = field(default=0, repr=False)
    _observed_cycles: int = field(default=0, repr=False)
    _observed_proposed: int = field(default=0, repr=False)
    _observed_accepted: int = field(default=0, repr=False)

    @property
    def paused(self) -> bool:
        return self._cooldown_remaining > 0

    def draft_budget(self) -> int:
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return 0
        return self.config.max_draft_tokens

    def record(self, *, proposed: int, accepted: int) -> bool:
        """Record one cycle. Returns True when this cycle tripped a pause.

        Cycles that proposed nothing are not observations: with no draft there
        is no wasted verify width to protect against, so they must not dilute
        the accept-rate window or push it toward a pointless pause.
        """
        if proposed <= 0:
            return False
        self._observed_cycles += 1
        self._observed_proposed += proposed
        self._observed_accepted += accepted
        if self._observed_cycles < self.config.warmup_cycles:
            return False
        rate = self._observed_accepted / self._observed_proposed
        # Reset the window either way so the next probe judges fresh behavior
        # rather than dragging early-conversation history forward.
        self._observed_cycles = 0
        self._observed_proposed = 0
        self._observed_accepted = 0
        if rate >= self.config.min_accept_rate:
            return False
        self._cooldown_remaining = self.config.cooldown_cycles
        return True


# step_fn(context_tokens, draft_tokens) -> greedy predictions.
#
# Returns `len(draft_tokens) + 1` token ids: element 0 is the model's next token
# after `context_tokens`, and element i is its next token after
# `context_tokens + draft_tokens[:i]`. Implementations may key off the context
# incrementally (KV cache) as long as that contract holds.
StepFn = Callable[[Sequence[int], Sequence[int]], Sequence[int]]


@dataclass
class PromptLookupEmission:
    """One verify cycle's accepted tokens plus its bookkeeping."""

    tokens: list[int]
    proposed: int
    accepted: int
    finish_reason: str | None = None


class PromptLookupDecoder:
    """Runtime-agnostic prompt-lookup decode loop."""

    def __init__(self, config: PromptLookupConfig) -> None:
        self._config = config
        self.stats = PromptLookupStats()

    def decode(
        self,
        *,
        prompt_tokens: Sequence[int],
        step_fn: StepFn,
        max_tokens: int,
        stop_token_ids: Sequence[int] = (),
        should_stop: Callable[[], bool] | None = None,
    ) -> Iterator[PromptLookupEmission]:
        """Yield accepted tokens cycle by cycle until stop, budget, or cancel.

        The emitted token sequence is identical to plain greedy decoding of the
        same model; only the number of forward passes differs.
        """
        prompt = [int(token) for token in prompt_tokens]
        if not prompt or max_tokens <= 0:
            return
        stop_ids = frozenset(int(token) for token in stop_token_ids)
        index = PromptLookupIndex(
            max_ngram=self._config.max_ngram,
            min_ngram=self._config.min_ngram,
        )
        index.extend(prompt)
        gate = _HysteresisGate(self._config)
        stats = self.stats
        remaining = max_tokens

        while remaining > 0:
            if should_stop is not None and should_stop():
                return
            # Read the pause state before `draft_budget()` consumes a cooldown
            # tick: after the call the counter has already been decremented, so
            # the final suppressed cycle of every cooldown would read as
            # un-paused and go uncounted.
            paused = gate.paused
            draft = index.propose(gate.draft_budget())
            predictions = [int(token) for token in step_fn(index.tokens, draft)]
            if not predictions:
                return
            stats.cycle_count += 1
            if not draft and paused:
                stats.paused_cycle_count += 1

            accepted = 0
            for draft_token, prediction in zip(draft, predictions):
                if draft_token != prediction:
                    break
                accepted += 1
            # Every emitted token is a prediction the target model made, which
            # is what preserves greedy identity: the accepted draft prefix is
            # bit-identical to predictions[:accepted], and predictions[accepted]
            # is the bonus token from the same forward.
            emitted = predictions[: accepted + 1]

            proposed = len(draft)
            stats.proposed_tokens += proposed
            stats.accepted_tokens += accepted
            stats.rejected_tokens += max(0, proposed - accepted)
            if gate.record(proposed=proposed, accepted=accepted):
                stats.fallback_count += 1

            finish_reason: str | None = None
            if len(emitted) > remaining:
                emitted = emitted[:remaining]
                finish_reason = "length"
            for position, token in enumerate(emitted):
                if token in stop_ids:
                    emitted = emitted[: position + 1]
                    finish_reason = "stop"
                    break

            index.extend(emitted)
            remaining -= len(emitted)
            stats.emitted_tokens += len(emitted)
            if finish_reason is None and remaining <= 0:
                finish_reason = "length"
            yield PromptLookupEmission(
                tokens=list(emitted),
                proposed=proposed,
                accepted=accepted,
                finish_reason=finish_reason,
            )
            if finish_reason is not None:
                return


def receipt_fields(stats: PromptLookupStats, config: PromptLookupConfig) -> dict[str, Any]:
    """Project stats onto the existing speculative receipt vocabulary.

    Reusing `speculative_*` keys keeps benchmark exports, diagnostics bundles,
    and the acceleration-profile surfaces working without new plumbing.
    """
    return {
        "speculative_acceptance_rate": stats.acceptance_rate,
        "speculative_rollback_rate": stats.rollback_rate,
        "speculative_accepted_tokens": stats.accepted_tokens,
        "speculative_rejected_tokens": stats.rejected_tokens,
        "speculative_fallback_count": stats.fallback_count,
        "speculative_num_draft_tokens": config.max_draft_tokens,
        "speculative_draft_model_configured": False,
    }
