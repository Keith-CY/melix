from __future__ import annotations

from typing import Callable, Sequence

import pytest

from worker.runtime.prompt_lookup import (
    PromptLookupConfig,
    PromptLookupDecoder,
    PromptLookupIndex,
    PromptLookupStats,
    _HysteresisGate,
    receipt_fields,
)


# ---------------------------------------------------------------------------
# Deterministic fake "models"
#
# A model here is `next_token(context) -> int`. `_step_fn` lifts one into the
# StepFn contract, so the accelerated loop and a plain baseline loop are driven
# by the exact same function — which is what makes greedy identity assertable.
# ---------------------------------------------------------------------------


NextToken = Callable[[Sequence[int]], int]


def _step_fn(next_token: NextToken, calls: list[int] | None = None):
    def step(context: Sequence[int], draft: Sequence[int]) -> list[int]:
        if calls is not None:
            calls.append(len(draft) + 1)
        working = list(context)
        predictions = [next_token(working)]
        for draft_token in draft:
            working.append(int(draft_token))
            predictions.append(next_token(working))
        return predictions

    return step


def _baseline(next_token: NextToken, prompt: Sequence[int], max_tokens: int, stop: Sequence[int] = ()) -> list[int]:
    """Plain greedy decode: one forward per token."""
    stop_ids = set(int(token) for token in stop)
    context = list(prompt)
    emitted: list[int] = []
    for _ in range(max_tokens):
        token = next_token(context)
        context.append(token)
        emitted.append(token)
        if token in stop_ids:
            break
    return emitted


def _accelerated(
    config: PromptLookupConfig,
    next_token: NextToken,
    prompt: Sequence[int],
    max_tokens: int,
    stop: Sequence[int] = (),
    calls: list[int] | None = None,
) -> tuple[list[int], PromptLookupStats, list[str | None]]:
    decoder = PromptLookupDecoder(config)
    emitted: list[int] = []
    finish_reasons: list[str | None] = []
    for emission in decoder.decode(
        prompt_tokens=prompt,
        step_fn=_step_fn(next_token, calls),
        max_tokens=max_tokens,
        stop_token_ids=stop,
    ):
        emitted.extend(emission.tokens)
        finish_reasons.append(emission.finish_reason)
    return emitted, decoder.stats, finish_reasons


def _passage_model(passage: Sequence[int], fallback_token: int = 999) -> NextToken:
    """Continues `passage` whenever the context ends with a passage prefix.

    Models the RAG / code-edit shape: the answer quotes a span that is already
    present in the prompt, so an n-gram draft from the prompt is usually right.
    """
    passage = [int(token) for token in passage]

    def next_token(context: Sequence[int]) -> int:
        for length in range(min(len(context), len(passage) - 1), 0, -1):
            if list(context[-length:]) == passage[:length]:
                return passage[length]
        return fallback_token

    return next_token


def _no_overlap_model() -> NextToken:
    """Emits a strictly increasing stream, so no n-gram ever recurs.

    Keyed on context length rather than a call counter: a StepFn evaluates the
    model once per draft position, so a stateful counter would make the model a
    function of call order instead of context and break the very determinism
    greedy identity is defined against.
    """

    def next_token(context: Sequence[int]) -> int:
        return 10_000 + len(context)

    return next_token


def _churning_model(alphabet_size: int = 5) -> NextToken:
    """Recurring n-grams whose continuations are position-dependent.

    This is the shape hysteresis exists for: the small alphabet makes suffixes
    recur constantly so drafts keep getting proposed, but the continuation
    depends on absolute position, so those drafts keep getting rejected.
    """

    def next_token(context: Sequence[int]) -> int:
        return (len(context) * 7) % alphabet_size

    return next_token


def _enabled_config(**overrides) -> PromptLookupConfig:
    base = {
        "enabled": True,
        "max_ngram": 4,
        "min_ngram": 2,
        "max_draft_tokens": 6,
        "min_accept_rate": 0.2,
        "warmup_cycles": 4,
        "cooldown_cycles": 8,
    }
    base.update(overrides)
    return PromptLookupConfig(**base)


# ---------------------------------------------------------------------------
# PromptLookupIndex
# ---------------------------------------------------------------------------


def test_index_empty_context_proposes_nothing() -> None:
    index = PromptLookupIndex(max_ngram=4, min_ngram=2)
    assert index.propose(4) == []


def test_index_proposes_continuation_of_repeated_suffix() -> None:
    index = PromptLookupIndex(max_ngram=4, min_ngram=2)
    # "1 2 3 4 5" appears once; context ends with "1 2", so the draft should be
    # the tokens that followed "1 2" earlier: 3, 4, 5.
    index.extend([1, 2, 3, 4, 5, 9, 9, 1, 2])
    assert index.propose(3) == [3, 4, 5]


def test_index_prefers_longest_matching_suffix() -> None:
    index = PromptLookupIndex(max_ngram=4, min_ngram=2)
    # Suffix "7 1 2" (len 3) recurs and continues with 3; the shorter "1 2"
    # would also match, but the longer match wins.
    index.extend([7, 1, 2, 3, 4, 0, 0, 8, 1, 2, 5, 7, 1, 2])
    assert index.propose(2) == [3, 4]


def test_index_unique_suffix_proposes_nothing() -> None:
    index = PromptLookupIndex(max_ngram=4, min_ngram=2)
    index.extend([1, 2, 3, 4, 5, 6])
    # "5 6" occurs only as the current suffix — nothing earlier to continue.
    assert index.propose(4) == []


def test_index_uses_earliest_occurrence() -> None:
    index = PromptLookupIndex(max_ngram=2, min_ngram=2)
    # "1 2" occurs at end-2 (followed by 30) and at end-6 (followed by 40).
    # First-occurrence-wins means the draft comes from the earlier span.
    index.extend([1, 2, 30, 77, 1, 2, 40, 88, 1, 2])
    assert index.propose(1) == [30]


def test_index_respects_min_ngram_floor() -> None:
    index = PromptLookupIndex(max_ngram=4, min_ngram=3)
    # Only a 2-token suffix recurs, which is below the floor.
    index.extend([1, 2, 50, 60, 70, 1, 2])
    assert index.propose(2) == []


def test_index_extends_incrementally_across_calls() -> None:
    incremental = PromptLookupIndex(max_ngram=3, min_ngram=2)
    for token in [4, 5, 6, 7, 8, 4, 5]:
        incremental.extend([token])
    whole = PromptLookupIndex(max_ngram=3, min_ngram=2)
    whole.extend([4, 5, 6, 7, 8, 4, 5])
    assert incremental.propose(3) == whole.propose(3) == [6, 7, 8]


def test_index_zero_budget_proposes_nothing() -> None:
    index = PromptLookupIndex(max_ngram=4, min_ngram=2)
    index.extend([1, 2, 3, 1, 2])
    assert index.propose(0) == []


# ---------------------------------------------------------------------------
# Greedy identity — the core correctness contract
# ---------------------------------------------------------------------------


def test_accelerated_output_matches_baseline_on_overlapping_workload() -> None:
    passage = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    model = _passage_model(passage)
    prompt = [90, 91] + passage + [92, 11]

    baseline = _baseline(model, prompt, 12)
    accelerated, stats, _ = _accelerated(_enabled_config(), model, prompt, 12)

    assert accelerated == baseline
    assert stats.accepted_tokens > 0
    # The prompt contains the passage, so drafts should mostly land.
    assert stats.acceptance_rate > 0.5


def test_accelerated_output_matches_baseline_on_adversarial_workload() -> None:
    prompt = [5, 6, 7, 8, 5, 6]

    baseline = _baseline(_no_overlap_model(), prompt, 20)
    accelerated, _stats, _ = _accelerated(_enabled_config(), _no_overlap_model(), prompt, 20)

    assert accelerated == baseline


def test_accelerated_output_matches_baseline_across_draft_budgets() -> None:
    passage = [21, 22, 23, 24, 25, 26]
    model = _passage_model(passage)
    prompt = [80] + passage + [81, 21, 22]
    baseline = _baseline(model, prompt, 10)

    for max_draft_tokens in (1, 2, 3, 5, 8):
        accelerated, _stats, _ = _accelerated(
            _enabled_config(max_draft_tokens=max_draft_tokens), model, prompt, 10
        )
        assert accelerated == baseline, f"diverged at max_draft_tokens={max_draft_tokens}"


def test_workload_without_any_repeat_costs_exactly_one_forward_per_token() -> None:
    # Distinct prompt tokens plus a never-repeating model means no suffix ever
    # recurs, so the loop degenerates to plain greedy decoding: one
    # single-token forward per emitted token, and zero wasted draft width.
    prompt = [1, 2, 3, 4, 5]
    model = _no_overlap_model()
    calls: list[int] = []

    accelerated, stats, _ = _accelerated(_enabled_config(), model, prompt, 6, calls=calls)

    assert accelerated == _baseline(model, prompt, 6)
    assert stats.proposed_tokens == 0
    assert calls == [1] * len(accelerated)


def test_config_normalizes_min_ngram_on_direct_construction() -> None:
    config = PromptLookupConfig(enabled=True, max_ngram=4, min_ngram=99)
    assert config.max_ngram == 4
    assert config.min_ngram == 4


# ---------------------------------------------------------------------------
# Throughput behavior
# ---------------------------------------------------------------------------


def test_overlapping_workload_needs_fewer_forwards_than_baseline() -> None:
    passage = list(range(200, 240))
    model = _passage_model(passage)
    prompt = [95, 96] + passage + [97] + passage[:3]
    calls: list[int] = []

    accelerated, stats, _ = _accelerated(
        _enabled_config(max_ngram=6, max_draft_tokens=8), model, prompt, 30, calls=calls
    )

    # Same tokens as baseline, but materially fewer forward passes.
    assert accelerated == _baseline(model, prompt, 30)
    assert len(calls) < len(accelerated)
    assert stats.cycle_count == len(calls)


def test_churning_workload_trips_hysteresis_and_pauses_drafting() -> None:
    prompt = [0, 1, 2, 3, 4, 0, 1]
    model = _churning_model()
    config = _enabled_config(warmup_cycles=3, cooldown_cycles=5, min_accept_rate=0.9)
    calls: list[int] = []

    accelerated, stats, _ = _accelerated(config, model, prompt, 40, calls=calls)

    # Correctness survives a workload that defeats drafting entirely.
    assert accelerated == _baseline(model, prompt, 40)
    # Drafts were proposed and mostly rejected, so the gate must have paused,
    # and paused cycles must be plain single-token forwards.
    assert stats.proposed_tokens > 0
    assert stats.acceptance_rate < config.min_accept_rate
    assert stats.fallback_count >= 1
    assert stats.paused_cycle_count >= 1
    assert calls.count(1) >= stats.paused_cycle_count
    assert max(calls) <= config.max_draft_tokens + 1


def test_paused_cycle_count_matches_every_suppressed_cycle() -> None:
    # The stat must count each cooldown cycle exactly once. Reading the gate's
    # pause state *after* draft_budget() consumed a tick undercounts the last
    # suppressed cycle of every cooldown, which the >= assertions elsewhere in
    # this file cannot catch.
    prompt = [0, 1, 2, 3, 4, 0, 1]
    config = _enabled_config(warmup_cycles=3, cooldown_cycles=5, min_accept_rate=0.9)
    calls: list[int] = []

    _accelerated_tokens, stats, _ = _accelerated(config, _churning_model(), prompt, 40, calls=calls)

    assert stats.fallback_count >= 1
    # Drafting resumed before the budget ran out, so every cooldown this run
    # entered also finished — which pins the expected count exactly.
    assert calls[-1] > 1
    # Each pause suppresses exactly cooldown_cycles cycles. Reading the gate's
    # pause state after draft_budget() consumed a tick loses the last one of
    # every cooldown, which the `>=` bounds used elsewhere cannot see.
    assert stats.paused_cycle_count == stats.fallback_count * config.cooldown_cycles


def test_hysteresis_gate_pauses_for_cooldown_then_resumes() -> None:
    config = _enabled_config(warmup_cycles=2, cooldown_cycles=3, min_accept_rate=0.5)
    gate = _HysteresisGate(config)

    # Warmup: the first poor cycle is not yet enough evidence to pause.
    assert gate.draft_budget() == config.max_draft_tokens
    assert gate.record(proposed=4, accepted=0) is False
    assert gate.draft_budget() == config.max_draft_tokens
    # Second poor cycle completes the window and trips the pause.
    assert gate.record(proposed=4, accepted=0) is True
    assert gate.paused is True

    # Drafting is suppressed for exactly cooldown_cycles cycles...
    assert [gate.draft_budget() for _ in range(config.cooldown_cycles)] == [0] * config.cooldown_cycles
    # ...then probing resumes rather than staying off permanently.
    assert gate.paused is False
    assert gate.draft_budget() == config.max_draft_tokens


def test_hysteresis_gate_stays_open_while_drafts_land() -> None:
    config = _enabled_config(warmup_cycles=2, cooldown_cycles=3, min_accept_rate=0.5)
    gate = _HysteresisGate(config)

    for _ in range(10):
        assert gate.draft_budget() == config.max_draft_tokens
        assert gate.record(proposed=4, accepted=4) is False
    assert gate.paused is False


def test_hysteresis_gate_ignores_cycles_without_proposals() -> None:
    config = _enabled_config(warmup_cycles=2, cooldown_cycles=3, min_accept_rate=0.9)
    gate = _HysteresisGate(config)

    # Cycles that proposed nothing carry no wasted verify width, so they must
    # not accumulate toward a pause.
    for _ in range(20):
        assert gate.record(proposed=0, accepted=0) is False
    assert gate.paused is False
    assert gate.draft_budget() == config.max_draft_tokens


def test_periodic_stream_reaches_high_acceptance() -> None:
    # A periodic token stream is the friendliest possible prompt-lookup
    # workload: once the period is in context, drafts keep landing.
    prompt = [0, 1, 2, 3, 4, 0, 1]
    model = _churning_model()
    accelerated, stats, _ = _accelerated(
        _enabled_config(min_accept_rate=0.0), model, prompt, 60
    )

    assert accelerated == _baseline(model, prompt, 60)
    assert stats.acceptance_rate > 0.8
    # Fewer cycles than emitted tokens is the throughput win.
    assert stats.cycle_count < stats.emitted_tokens


# ---------------------------------------------------------------------------
# Stop, budget, and cancellation handling
# ---------------------------------------------------------------------------


def test_stop_token_truncates_mid_draft_and_reports_stop() -> None:
    passage = [41, 42, 43, 44, 45, 46]
    model = _passage_model(passage)
    prompt = [60] + passage + [61, 41]

    accelerated, _stats, finish_reasons = _accelerated(
        _enabled_config(), model, prompt, 20, stop=[44]
    )

    assert accelerated == _baseline(model, prompt, 20, stop=[44])
    assert accelerated[-1] == 44
    assert 44 not in accelerated[:-1]
    assert finish_reasons[-1] == "stop"


def test_max_tokens_truncates_emission_and_reports_length() -> None:
    passage = list(range(51, 71))
    model = _passage_model(passage)
    prompt = [59] + passage + [58] + passage[:2]

    accelerated, _stats, finish_reasons = _accelerated(_enabled_config(), model, prompt, 5)

    assert len(accelerated) == 5
    assert accelerated == _baseline(model, prompt, 5)
    assert finish_reasons[-1] == "length"


def test_should_stop_cancels_before_next_cycle() -> None:
    passage = list(range(81, 101))
    model = _passage_model(passage)
    prompt = [79] + passage + [78] + passage[:2]
    decoder = PromptLookupDecoder(_enabled_config())
    cancelled = {"value": False}

    emitted: list[int] = []
    for emission in decoder.decode(
        prompt_tokens=prompt,
        step_fn=_step_fn(model),
        max_tokens=100,
        should_stop=lambda: cancelled["value"],
    ):
        emitted.extend(emission.tokens)
        cancelled["value"] = True

    assert emitted  # the first cycle ran
    assert len(emitted) < 100  # and the second was cancelled


def test_empty_prompt_and_zero_budget_emit_nothing() -> None:
    decoder = PromptLookupDecoder(_enabled_config())
    assert list(decoder.decode(prompt_tokens=[], step_fn=_step_fn(_no_overlap_model()), max_tokens=8)) == []
    assert list(decoder.decode(prompt_tokens=[1, 2], step_fn=_step_fn(_no_overlap_model()), max_tokens=0)) == []


def test_empty_prediction_stops_the_loop() -> None:
    decoder = PromptLookupDecoder(_enabled_config())
    emissions = list(
        decoder.decode(
            prompt_tokens=[1, 2, 3],
            step_fn=lambda context, draft: [],
            max_tokens=4,
        )
    )
    assert emissions == []


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def test_config_defaults_to_disabled_without_ext() -> None:
    assert PromptLookupConfig.from_ext(None).enabled is False
    assert PromptLookupConfig.from_ext({}).enabled is False
    assert PromptLookupConfig.from_ext({"melix.prompt_lookup.enabled": "false"}).enabled is False


def test_config_reads_knobs_from_ext() -> None:
    config = PromptLookupConfig.from_ext(
        {
            "melix.prompt_lookup.enabled": "true",
            "melix.prompt_lookup.max_ngram": "5",
            "melix.prompt_lookup.min_ngram": "3",
            "melix.prompt_lookup.max_draft_tokens": "12",
            "melix.prompt_lookup.min_accept_rate": "0.35",
            "melix.prompt_lookup.warmup_cycles": "6",
            "melix.prompt_lookup.cooldown_cycles": "9",
        }
    )
    assert config.enabled is True
    assert config.max_ngram == 5
    assert config.min_ngram == 3
    assert config.max_draft_tokens == 12
    assert config.min_accept_rate == pytest.approx(0.35)
    assert config.warmup_cycles == 6
    assert config.cooldown_cycles == 9


def test_config_clamps_and_ignores_malformed_values() -> None:
    config = PromptLookupConfig.from_ext(
        {
            "melix.prompt_lookup.enabled": "1",
            "melix.prompt_lookup.max_ngram": "-4",
            "melix.prompt_lookup.max_draft_tokens": "not-a-number",
            "melix.prompt_lookup.min_accept_rate": "9.5",
        }
    )
    assert config.enabled is True
    assert config.max_ngram == 1  # clamped to the minimum
    assert config.max_draft_tokens == 8  # default kept for unparseable input
    assert config.min_accept_rate == pytest.approx(1.0)  # clamped to the maximum


def test_config_min_ngram_never_exceeds_max_ngram() -> None:
    config = PromptLookupConfig.from_ext(
        {
            "melix.prompt_lookup.enabled": "yes",
            "melix.prompt_lookup.max_ngram": "3",
            "melix.prompt_lookup.min_ngram": "7",
        }
    )
    assert config.max_ngram == 3
    assert config.min_ngram == 3


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


def test_receipt_fields_project_onto_speculative_vocabulary() -> None:
    stats = PromptLookupStats(
        cycle_count=4,
        proposed_tokens=10,
        accepted_tokens=6,
        rejected_tokens=4,
        fallback_count=1,
    )
    fields = receipt_fields(stats, _enabled_config(max_draft_tokens=6))

    assert fields["speculative_acceptance_rate"] == pytest.approx(0.6)
    assert fields["speculative_rollback_rate"] == pytest.approx(0.4)
    assert fields["speculative_accepted_tokens"] == 6
    assert fields["speculative_rejected_tokens"] == 4
    assert fields["speculative_fallback_count"] == 1
    assert fields["speculative_num_draft_tokens"] == 6
    assert fields["speculative_draft_model_configured"] is False


def test_receipt_rates_are_zero_without_proposals() -> None:
    fields = receipt_fields(PromptLookupStats(), _enabled_config())
    assert fields["speculative_acceptance_rate"] == 0.0
    assert fields["speculative_rollback_rate"] == 0.0
