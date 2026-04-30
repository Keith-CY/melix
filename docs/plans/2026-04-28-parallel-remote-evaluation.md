# Parallel Remote Evaluation Plan

## Summary

Melix evaluation should be able to run multiple independent remote providers in
one operator command. This slice keeps the existing single-target evaluation RPC
contract and adds concurrency at the CLI orchestration layer, while making the
Python worker's evaluation job id allocation safe for concurrent requests.

## Scope

- `melix eval run` accepts multiple remote server targets for remote evaluation.
- Multiple remote targets are dispatched concurrently by the Swift CLI runner.
- Each target still becomes an independent control-plane evaluation request and
  worker job, preserving existing result, prediction, failure, prompt snapshot,
  scoring, and dialogue trace artifact formats.
- The Python worker reserves evaluation job ids atomically so concurrent
  provider runs cannot share `eval-xxxx` or overwrite artifacts.
- Local model and Hugging Face repo evaluation remain single target.

## CLI Contract

Existing single-target syntax remains valid:

```bash
melix eval run --remote-server-id DeepSeek --remote-model deepseek-v4-pro ...
```

New multi-target syntax repeats remote server ids and optionally repeats remote
models in the same order:

```bash
melix eval run \
  --remote-server-id DeepSeek --remote-model deepseek-v4-pro \
  --remote-server-id Gemini --remote-model gemini-2.5-flash \
  --remote-server-id GML --remote-model glm-5.1 \
  --remote-server-id OpenAI --remote-model gpt-5.4 \
  --remote-parallelism 4 ...
```

When `--remote-model` is omitted for remote targets, Melix uses each remote
server's configured default model. `--remote-parallelism` caps concurrent
provider jobs; the default is all selected remote targets.

## Data Flow

1. The CLI parses the remote target list into ordered `{remote_server_id,
   remote_model_id}` items.
2. Shared suite/source/profile/prompt parameters are resolved once per suite.
3. The runner dispatches one `ControlPlaneEvaluationRequest` per remote target
   and suite, bounded by `remote_parallelism`.
4. The control plane keeps the existing single remote target validation and
   worker request translation.
5. The Python worker allocates a unique job id under `MELIX_EVALUATION_JOBS_ROOT`
   before artifact creation.
6. Each provider writes a separate `event-extraction/<job-id>` tree and a
   persisted `runs/<job-id>` record.

## Isolation Requirements

- API keys remain transient inside each request and must not enter persisted job
  parameters, outputs, reports, or comments.
- Gold JSONL is read-only and shared safely.
- Prompt snapshots are written per provider job.
- Provider rate limits remain per remote server target; Melix does not merge or
  globalize rate limits across providers in this slice.
- Provider-level HTTP failures that are expected to repeat for every row
  (`401`, `403`, `404`, `429`, and `5xx`) abort the current provider job early.
  The worker writes `event_eval_error.json` plus the partial prediction,
  failure, and dialogue trace JSONL artifacts before surfacing the provider
  error.
- Event extraction writes `event_eval_dialogue_traces.jsonl` with per-dialogue
  status, latency, throttling, size, event-count, error-code, and provider usage
  metadata. It must not include API keys, base URLs, prompt text, request
  payloads, or gold events.
- Event extraction writes `event_eval_row_audit.jsonl` with per-dialogue
  optimal event alignment pairs, unmatched indices, and candidate scores. Event
  matching uses deterministic soft similarity only to align events; final field
  TP/FP/FN remains exact string set scoring.
- Result ordering returned by the CLI is stable by input target order, then suite
  order, even if providers finish out of order.

## Tests

- Swift parser: repeated `--remote-server-id` and `--remote-model` values build
  an ordered remote target list; omitted models use server defaults later.
- Swift runner: multiple remote targets are dispatched concurrently, preserve
  target ordering in returned results, and forward each resolved credential only
  to its own request.
- Python worker core: concurrent job id allocation returns unique ids and
  reserves corresponding run directories.
- Python event extraction: remote provider rate-limit responses abort without
  repeating the same failure for every row and write a structured error log.
- Python event extraction: dialogue trace rows cover success, row-level failure,
  rate-limit abort, provider usage normalization, and rate-limit sleep timing.
- Python event extraction: scorer tests cover reordered events, low-similarity
  unmatched events, exact field scoring after soft alignment, row audit output,
  and global optimal matching.
