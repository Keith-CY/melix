# Evaluation Frozen Prompts

## Summary

Melix adds a local Evaluation Prompt registry for event extraction evaluation.
The v1 scope is limited to `event_extraction_weighted_f1`; other evaluation
suites keep their current prompt and scoring behavior.

Frozen prompts are immutable revisions. Editing a frozen revision creates a new
draft revision so completed evaluation runs remain reproducible.

## Scope

- Store evaluation prompts under `$MELIX_HOME/state/evaluation-prompts.json`.
- Ship a read-only built-in baseline prompt. `baseline.v1` preserves the
  original direct `events` JSON prompt; the default `baseline.v2` uses the
  stage-1 `Segment Metadata Candidates` prompt for `top200_final.jsonl`.
- Allow custom prompts to be created, updated as drafts, frozen, listed, shown,
  and archived from the CLI.
- Allow the macOS Evaluation view to select a prompt and edit/freeze draft
  prompts.
- Resolve `eval run --eval-prompt-id` and optional
  `--eval-prompt-revision` before dispatch.
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
melix eval run ... --eval-prompt-id ID [--eval-prompt-revision REV]
```

The default eval prompt is the built-in baseline prompt's latest frozen
revision when no prompt id is provided.

## Worker Flow

The Swift CLI resolves the selected prompt into transient evaluation
parameters. The Python event extraction path consumes those transient fields,
removes prompt content from persisted job parameters, writes
`prompt_snapshot.json`, and passes a resolved prompt spec into the remote
provider client. When the selected prompt is the stage-1 candidate prompt, the
worker sends a structured input payload containing `segment`,
`participant_set`, and `conversation`, then converts returned
`event_candidates` into the scorer-compatible `events` shape.

If prompt examples are later populated from a gold JSONL source, every example
must include `dialogue_id`; the run rejects prompt examples whose ids overlap
the evaluation rows.

## Verification

- Swift unit tests cover prompt store lifecycle, built-in read-only behavior,
  frozen revision immutability, deterministic hashes, CLI parsing, and eval run
  prompt parameter forwarding.
- Python tests cover selected prompt payloads for OpenAI-compatible and Gemini
  clients, prompt snapshot output, prompt content non-persistence in job
  parameters, no gold leakage, and example overlap rejection.
- macOS tests cover prompt picker/editor state, draft editing, freeze
  behavior, and eval run parameter forwarding.
- Scorer regression tests must continue to pass without schema changes.
