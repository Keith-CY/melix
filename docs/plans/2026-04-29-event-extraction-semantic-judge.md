# Event Extraction Semantic Judge Scoring

## Summary

Melix Evaluation keeps the existing deterministic `event_extraction_weighted_f1`
outputs and adds optional semantic judge scoring artifacts. The judge reuses the
Remote Server target model, credentials, provider adapters, and rate limits. It
does not introduce a new server abstraction.

The judge only decides whether event pairs or field values are semantically
equivalent. Melix still computes TP, FP, FN, precision, recall, F1, and weighted
F1 locally.

## Behavior

- `eval run` can receive an optional judge target:
  - `--semantic-judge-remote-server-id`
  - `--semantic-judge-model`
- The evaluated remote provider and judge remote provider are independent.
- The exact event extraction summary/details/row audit remain the default
  comparable output.
- When a judge target is configured, Melix additionally writes:
  - `event_eval_semantic_summary.json`
  - `event_eval_semantic_details.jsonl`
  - `event_eval_semantic_row_audit.jsonl`
  - `event_eval_judge_audit.jsonl`
- Judge API keys are transient. They must not appear in job parameters,
  summaries, traces, logs, or persisted artifacts.
- Judge failures do not fail the main evaluation. Exact artifacts remain valid;
  semantic artifacts are marked `partial` or `failed`.

## Scoring Rules

- Event alignment is still one-to-one within a `dialogue_id`.
- Deterministic exact/high-confidence local matches can skip the judge.
- Ambiguous event candidates are sent to the judge with compact context.
- Matched event fields are scored by one-to-one semantic value matching.
- `action` field scoring additionally supports semantic split/merge group
  matching. A single action value can match a supported group of up to three
  values on the other side, and the accepted group consumes all participating
  values so they do not also count as FP/FN.
- Malformed, uncertain, or failed judge decisions count as non-matches.
- Field weights remain:
  - `action = 0.35`
  - `actor = 0.30`
  - `time = 0.25`
  - `location = 0.10`

## Observability

The semantic summary records safe metadata only:

- judge remote server id
- judge model id
- judge prompt version
- judge prompt hash
- judge call count
- cache hit count
- failure count
- semantic status

The judge audit records the decision inputs and outputs needed for review, but
never includes API keys, base URLs, or full prompt text.

## Prompt Versioning

`semantic-judge.v2` distinguishes `kind=event` from `kind=field`. Event
alignment may treat different action granularities as one real-world event, for
example `出来转转` vs `见面,逛街`, while field scoring remains stricter. The
prompt includes hard negatives for conflicting times such as `明天` vs `27号`,
same-place same-time but different participant events, hallucinations, and
duplicate predictions.

`semantic-judge.v3` keeps that boundary and adds follow-up audit examples for
`见面聊天` vs `见面,聊聊`, coarse time matches such as `今天直到夕阳西下` vs
`今天`, and party-event alignment such as `有大聚会` vs `参加聚会` while still
requiring unsupported actor fields to score as non-matches.

`semantic-judge.v4` adds action split/merge guidance and actor relation
boundaries. It can judge `["吃饭见面"]` as equivalent to `["吃饭","见面"]`,
`["见面聊天"]` as equivalent to `["见面","聊聊"]`, and `["碰头聚聚"]` as
equivalent to `["见面","聚聚"]` when they describe one event. Named relation
aliases such as `speaker_1的朋友阿菜` may match `阿菜`, but related third
parties such as `speaker_1的表姐` must not match the speaker slot itself.
Preparation actions such as `拿位` may help event alignment but should not
receive action TP against `见面`.

## Verification

- Python scorer tests for semantic event alignment, semantic field matching,
  action split/merge matching, actor relation aliases, non-equivalent fields,
  judge failure, and cache hits.
- Python evaluation-core tests for semantic artifact creation and secret
  non-persistence.
- Swift CLI parser/runner tests for judge target argument parsing and parameter
  forwarding.
- `make py-test`
- `make swift-test`
