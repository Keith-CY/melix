# Confidence-adjusted semantic F1 and v23 canary

Status: implementation in progress
Date: 2026-06-02
Report issue: https://github.com/lay2dev/train-report/issues/3

## Scope

Run an eval-0997 canary first, then expand only to the recent six LoRA eval
reports after the canary passes.

Recent six:

- eval-0997 / lora-dialogue-20260529t172640z
- eval-0994 / lora-dialogue-20260529t151745z
- eval-0991 / lora-dialogue-20260529t102614z
- eval-0988 / lora-dialogue-20260529t094617z
- eval-0985 / lora-dialogue-20260529t090958z
- eval-0982 / lora-dialogue-20260529t081852z

Out of scope for this round:

- Optional or allowed non-target event taxonomy.
- Retraining with v23. The first prompt check is inference-only with the
  existing v22-trained adapter.
- Older report history outside the recent six.

## Current Constraints

This worktree was created from the current origin/main so implementation does
not inherit the stale branch state from the earlier soft semantic metric
worktree.

The extraction prompt should remain external/private, following the v22 prompt
handling pattern. Do not copy the private prompt body into repository code or
public report artifacts.

## Accepted Scoring Model

Use confidence-adjusted semantic event matching, scheme B.

Constants:

- `SEMANTIC_EVENT_MATCH_MIN_CONFIDENCE = 0.20`
- `SEMANTIC_HIGH_CONFIDENCE_THRESHOLD = 0.50`
- `scoring_mode = event_extraction_semantic_confidence_adjusted_weighted_f1.v1`

Event matching:

- A pair can enter event matching only when the event judge returns
  `equivalent=true` and `confidence >= 0.20`.
- `equivalent=false` never enters matching. Confidence is confidence in the
  boolean decision, not a similarity score.
- Matching weight is `event_match_confidence * field_weighted_f1`.
- A pair with `0.20 <= confidence < 0.50` is a low-confidence match, not an
  unmatched pair.
- A pair with `confidence >= 0.50` is a high-confidence match.

Field scoring:

- Exact field match: `1.0`.
- Semantic field match: field judge confidence.
- Non-match: `0.0`.
- Empty-gold and empty-pred fields are inactive and must not consume field
  weight.
- Active field weights are renormalized over active fields.

Matched event score:

```text
legacy_weighted_f1 = weighted field score before event confidence
weighted_f1 = event_match_confidence * legacy_weighted_f1
```

Aggregation:

- `overall_weighted_f1` uses the new confidence-adjusted matched event score.
- `soft_semantic_event_precision`, `soft_semantic_event_recall`,
  `soft_semantic_event_f1`, `soft_semantic_event_f0_5`, and
  `matched_event_quality` use the same confidence-adjusted score sum.
- `soft_semantic_event_f0_5` is the quality-priority diagnostic: it weights
  precision more than recall, so missing gold events hurt less than
  hallucinated or low-quality matched predictions. It must not replace the
  primary F1 gate because otherwise a model can win by extracting too few
  events.
- The summary manifest records the previous scoring mode in
  `supersedes_scoring_mode`.

## Detail JSONL Contract

`event_eval_semantic_details.jsonl` must include the matching and scoring
evidence needed to debug each row.

Event-level fields:

- `active_fields`
- `inactive_fields`
- `field_weight_sum`
- `field_weight_policy`
- `event_match_confidence`
- `event_match_confidence_tier`
- `legacy_weighted_f1`
- `confidence_adjusted_weighted_f1`
- `weighted_f1`
- `scoring_mode`

Per-field fields:

- `active`
- `weight`
- `score_contribution`
- `inactive_reason`
- `semantic_match_confidence`, when a semantic field judge was used

The old field-only score should remain available in details as
`legacy_weighted_f1`; the headline `weighted_f1` should be the new
confidence-adjusted score.

## Semantic Judge v5

Add a semantic judge prompt version that separates event identity from field
correctness.

Event-level judge target:

- Decide whether gold and pred describe the same real-world event instance.
- Do not reject a same-event pair solely because actor, time, location, or
  action values differ.
- Field differences should be handled by field-level scoring.

Guardrails:

- Same time, same location, or same topic alone is not enough.
- Unconfirmed, proposed, cancelled, or denied events should not be matched to a
  confirmed gold event.
- Split/merge cases should be low-confidence unless the event identity is
  genuinely the same single event.
- Do not use confidence as partial similarity when `equivalent=false`.

The prompt version and cache key must change so v5 decisions cannot collide
with prior judge-cache entries.

## Extraction Prompt v23

Create v23 as a targeted amendment to v22, not a full rewrite.

Amendments:

- Strengthen filtering of unconfirmed proposals and events that were not
  accepted or confirmed.
- Strengthen third-party actor ownership. If the dialogue mentions another
  person performing the event, do not assign that event to a speaker unless the
  speaker is the actor.
- Filter low-value non-target events that are not part of the target extraction
  scope.
- Split phase events when arrival, departure, return, or similar phases are
  separate events.
- Avoid merging multiple gold events into one interval-like prediction.

First validation is inference-only with the existing v22-trained adapter and
the v23 inference prompt. Do not retrain in this round.

## Eval-0997 Corrected Gold

Create a corrected eval-0997 gold artifact before prompt-quality judgment.

The corrected gold should address the feedback categories:

- Add missing gold events where the LoRA prediction is valid and gold omitted
  the event.
- Correct mislabeled gold fields.
- Preserve clear non-target or unconfirmed predicted events as false positives.
- Keep the optional/allowed event question as a follow-up note only.

Report label-fix gain, scorer gain, and prompt gain separately so the v23
prompt is not credited for gold cleanup or scorer relaxation.

## Canary Matrix

Run four cells for eval-0997:

1. v22 output + old scorer
2. v22 output + new confidence-adjusted scorer
3. v23 output + old scorer
4. v23 output + new confidence-adjusted scorer

Use corrected gold for prompt-quality judgment. If the old-gold baseline is
also shown, label it explicitly as historical baseline only.

Primary success criterion:

- Feedback-point pass/fail.

Secondary success criterion:

- Semantic F1 movement, separated into label-fix, scorer, and prompt effects.

## Report Publishing

Publish the eval-0997 canary under train-report with title:

```text
Eval-0997 confidence-adjusted scorer and v23 prompt canary
```

Required tables:

- Scorer-only effect
- Prompt-only effect
- Final candidate vs current baseline
- Feedback-point checklist

Every artifact should declare:

- eval id
- report run id
- adapter/output source
- gold source
- prompt version
- semantic judge prompt version
- scoring mode
- scorer code provenance

After eval-0997 passes, overwrite semantic outputs only in the recent six
report directories and push train-report.

## Verification Gates

Melix tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
UV_PYTHON=3.12 \
uv run --project services/mlx-worker-python --extra mlx pytest \
  services/mlx-worker-python/tests/test_event_extraction.py
```

Artifact checks:

- Details JSONL row count matches scored dialogue/event rows.
- Every matched event has `event_match_confidence`.
- Low-confidence matches are marked with a confidence tier.
- Empty-gold and empty-pred fields are inactive.
- Active field weights sum to 1.0 after renormalization.
- Summary formulas equal the values recomputed from details.
- Report artifacts identify whether they use old or corrected gold.

Operational checks:

- Do not overwrite older report history outside the recent six.
- Do not publish private prompt bodies.
- Do not treat optional/allowed events as solved in this issue.
