# Evaluation Frozen Prompts

## Summary

Melix adds a local Evaluation Prompt registry for event extraction evaluation.
The v1 scope is limited to `event_extraction_weighted_f1`; other evaluation
suites keep their current prompt and scoring behavior.

`eval run` also supports one-off ad hoc system prompts for any evaluation
suite. These prompts are not registry revisions; they are a per-run override
for operator experiments and apply to every suite requested by that invocation.

Frozen prompts are immutable revisions. Editing a frozen revision creates a new
draft revision so completed evaluation runs remain reproducible.

## Scope

- Store evaluation prompts under `$MELIX_HOME/config/evaluation-prompts.json`.
- Ship a read-only built-in baseline prompt. `baseline.v1` preserves the
  original direct `events` JSON prompt; `baseline.v2` preserves the stage-1
  `Segment Metadata Candidates` prompt; the default `baseline.v3` uses a
  Chinese direct JSON event-extraction prompt for `top200_final.jsonl`.
- Allow custom prompts to be created, updated as drafts, frozen, listed, shown,
  and archived from the CLI.
- Allow the macOS Evaluation view to select a prompt and edit/freeze draft
  prompts.
- Resolve `eval run --eval-prompt-id` and optional
  `--eval-prompt-revision` before dispatch.
- Accept exactly one of `eval run --eval-prompt TEXT`,
  `--eval-prompt-file PATH`, or `--eval-prompt-id ID`. The text/file forms are
  one-off prompts for all suites in the run and use the ad hoc metadata identity
  `ad-hoc.evaluation.prompt` / `ad-hoc`.
- Event extraction runs record `prompt_id`, `prompt_revision_id`, and
  `prompt_content_hash`, and write `prompt_snapshot.json` beside run artifacts.
- Provider calls receive only the selected system prompt, optional frozen
  examples, and the current dialogue. Gold events for the current row are never
  included in provider context.

## Data Model

`EvaluationPrompt`:

- `id`
- `title`
- `task_kind = event_extraction`
- `scoring_mode = event_extraction_weighted_f1`
- `latest_revision_id`
- `archived`
- `created_at`
- `updated_at`

`EvaluationPromptRevision`:

- `revision_id`
- `status = draft | frozen`
- `system_prompt`
- optional `examples`
- `content_hash`
- `created_at`
- `updated_at`

The content hash is deterministic over the task kind, scoring mode, system
prompt, and sorted JSON representation of examples.

## CLI

```bash
melix eval prompt list [--json]
melix eval prompt show --prompt-id ID [--revision-id REV] [--json]
melix eval prompt create --prompt-id ID --title TITLE --system-prompt-file PATH [--json]
melix eval prompt update --prompt-id ID --system-prompt-file PATH [--json]
melix eval prompt freeze --prompt-id ID [--revision-id REV] [--json]
melix eval prompt archive --prompt-id ID [--json]
melix eval run ... --eval-prompt TEXT
melix eval run ... --eval-prompt-file PATH
melix eval run ... --eval-prompt-id ID [--eval-prompt-revision REV]
```

The default event-extraction eval prompt is the built-in baseline prompt's
latest frozen revision when no prompt id is provided. For other suites, no
registry prompt is applied unless a one-off prompt is passed.

## Worker Flow

The Swift CLI resolves the selected prompt into transient evaluation
parameters. The Python event extraction path consumes those transient fields,
removes prompt content from persisted job parameters, writes
`prompt_snapshot.json`, and passes a resolved prompt spec into the remote
provider client. When the selected prompt is the default `baseline.v3` direct
JSON prompt, the worker sends only a structured input payload containing
`dialogue_id` and `dialogue`; gold `events` are never included. The model is
asked to return `dialogue_id`, `events`, event order hints, and digest text; the
worker still normalizes outputs into the scorer-compatible `actor`, `time`,
`location`, `action`, and locally derived `digest` shape. When the selected
prompt is the historical stage-1 candidate prompt, the worker sends `segment`,
`participant_set`, and `conversation`, then converts returned
`event_candidates` into the same scorer-compatible shape.

If prompt examples are later populated from a gold JSONL source, every example
must include `dialogue_id`; the run rejects prompt examples whose ids overlap
the evaluation rows.

For non-event-extraction suites, one-off prompt text is prepended into the
system message after the suite's fixed instruction and before any sample-level
system text. The worker removes the full prompt text from persisted job
parameters and records the prompt character count as a metric so report artifacts
make the prompt-control surface auditable.

## Verification

- Swift unit tests cover prompt store lifecycle, built-in read-only behavior,
  frozen revision immutability, deterministic hashes, CLI parsing, and eval run
  prompt parameter forwarding, including one-off prompt text and file inputs.
- Python tests cover selected prompt payloads for OpenAI-compatible and Gemini
  clients, prompt snapshot output, prompt content non-persistence in job
  parameters, no gold leakage, example overlap rejection, and ad hoc prompt
  insertion for generic evaluation suites.
- macOS tests cover prompt picker/editor state, draft editing, freeze
  behavior, and eval run parameter forwarding.
- Scorer regression tests must continue to pass without schema changes.
