# Gemma 4 Annotation Feedback Incorporation

Melix Evaluation incorporates Gemma 4 annotation feedback without directly
modifying the local gold dataset. The feedback pass produces a patch plan for
human review, adds a new built-in frozen prompt revision, and keeps prior
evaluation results reproducible through explicit revision selection.

## Scope

- Read annotation feedback from
  `/Users/ChenYu/Downloads/google_gemma-4-31B-it-annotations.jsonl`.
- Read the follow-up v5 smoke feedback from
  `/Users/ChenYu/Downloads/google_gemma-4-31B-it-annotations (1).jsonl`.
- Do not overwrite `/Users/ChenYu/Downloads/top200_final.jsonl`.
- Generate `.runtime/evaluations/feedback/google_gemma-4-31B-it-gold-patch-plan.json`
  and `.md` with per-note triage.
- Generate `.runtime/evaluations/feedback/google_gemma-4-31B-it-v5-feedback-patch-plan.json`
  and `.md` for the follow-up v5 feedback pass.
- Add built-in event extraction prompt revisions `baseline.v5` and
  `baseline.v6`; `baseline.v6` is the default latest revision.
- Preserve `baseline.v1`, `baseline.v2`, `baseline.v3`, `baseline.v4`, and
  `baseline.v5` for historical reproduction.
- Add semantic judge prompt versions `semantic-judge.v2`, `semantic-judge.v3`,
  and `semantic-judge.v4` for the feedback cases that affect event alignment,
  field equivalence, and action split/merge scoring.
- Keep semantic judge scoring deterministic around the final metric formula:
  judge decisions can identify semantic equivalence, but Melix computes
  TP/FP/FN/F1 locally.

## Prompt Revision v5

`baseline.v5` keeps the Chinese JSON event schema from `baseline.v4` and adds
more explicit feedback-derived constraints:

- continuous ranges such as `1月6号到9号之间` remain one time expression;
- available or candidate times do not become event times until accepted;
- same place and same time do not imply shared event actors;
- duplicate booking, reservation, meetup, and meal descriptions collapse into
  one main event when they refer to the same arrangement;
- vague third-party relation words stay in action detail unless the third
  party is the true event subject;
- micro preparation actions such as taking seats are merged into the main
  meeting or meal;
- uncertain proper-name actions can use a safer parent action such as `做检查`;
- compound social activities stay as one event unless the dialogue supports
  separate real-world actions.
- same-time same-place meals stay separate when the participants are not doing
  one shared event;
- booking, taking seats, and other preparation steps are not independent events
  unless they have standalone action value;
- ambiguous `糖筛/唐筛` wording can be generalized to `做检查`.

## Prompt Revision v6

`baseline.v6` keeps `baseline.v5` and adds recall-oriented constraints from
the follow-up feedback:

- clearly stated past/background events such as `周日新买裙子` should be
  extracted;
- committed contact actions such as `明天打给你` are valid events when they are
  explicitly scheduled;
- flight or plane events with explicit times, such as `周一晚上11点下飞机` and
  `周二晚上7点上飞机`, should be extracted as separate events;
- vague third-party relation words such as coworker, friend, and cousin stay in
  action detail unless the third party is the actual event subject;
- preparation actions, duplicate gatherings, and micro-actions remain merged
  into the main event unless they have standalone value.

## Judge Prompt v2/v3

`semantic-judge.v2` separates event alignment from field scoring:

- `kind=event` can match two predictions to the same real-world event when the
  action granularity differs, such as `出来转转` vs `见面,逛街`.
- `kind=field` remains stricter; for example, `拿位` can support event
  alignment but should not automatically count as action-equivalent to `见面`.
- `做唐筛` / `做糖筛` / `做检查` can be action-equivalent when the dialogue
  clearly identifies the same check.
- hard negatives such as `明天` vs `27号`, hallucinated events, duplicate
  predictions, and same-place same-time but different actor events remain
  non-equivalent.

`semantic-judge.v3` adds follow-up examples:

- `见面聊天` can match `见面,聊聊` for action field scoring when both refer to
  the same meetup conversation;
- `今天直到夕阳西下` can match the coarser `今天` time value in the same event
  context;
- `有大聚会` and `参加聚会` can align as the same party event, but unsupported
  actors still do not receive actor TP;
- same day/topic with different subjects and hallucinated events remain hard
  negatives.

`semantic-judge.v4` adds the latest annotation feedback:

- action field scoring can match split/merged compound actions such as
  `["吃饭","见面"]` vs `["吃饭见面"]`;
- named relation aliases such as `speaker_1的朋友阿菜` can match `阿菜`, while
  related third parties such as `speaker_1的表姐` do not match the speaker slot;
- action object or role loss, for example `去接speaker_2` vs a generic `接站`,
  should not receive action TP unless context preserves the missing object;
- preparation actions such as `拿位` may align the event but remain non-TP at
  action field level unless the compared action group truly describes the same
  action.

## Feedback Patch Plan

The patch plan classifies each annotation note as:

- `gold_patch`: likely gold data should change, but still requires human
  confirmation before editing the dataset.
- `prompt_rule`: prompt behavior should discourage the model error.
- `judge_or_scorer_rule`: semantic judge/scorer can reasonably treat the pair
  as equivalent or non-equivalent.
- `pred_error`: prediction-only error; it must not become a gold patch.
- `needs_triage`: insufficient signal for an automatic recommendation.

Each item records `dialogue_id`, event indices, match status, the original note,
feedback targets such as `evaluation_prompt` or `judge_prompt`, the related
gold/pred events when available, the recommended action, and whether human
confirmation is required.

## Verification

- Unit tests cover v5 default prompt resolution, v6 default prompt resolution,
  historical prompt resolution, semantic judge prompt versioning, action
  split/merge scoring, patch-plan target classification, and patch-plan
  JSON/Markdown output.
- Targeted Python tests cover prompt revision, semantic scorer guards, and the
  patch-plan generator.
- A Gemma 4 top20 smoke should be run after implementation with the current
  `top200_final.jsonl` and the configured judge server.
