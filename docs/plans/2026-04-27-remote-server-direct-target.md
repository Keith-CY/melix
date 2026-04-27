# Remote Server Direct Target

## Summary

Melix adds Remote Server as a direct Chat and Evaluation target for remote
providers. The v1 target is intentionally not exposed through the local gateway
and does not participate in LoRA, local model ids, or local runtime lifecycle.

## Scope

- Remote Server state is stored under Melix local state with visible metadata
  only.
- Remote Server API keys are stored in the local secrets store and referenced by
  credential id.
- Chat can dispatch directly to a remote provider target through the Swift
  control plane.
- Evaluation can forward a transient remote provider target to the Python
  worker without copying the API key into persisted job parameters.
- `event_extraction_weighted_f1` evaluates `top200_final.jsonl`-style event
  extraction predictions with exact set matching over `actor`, `time`,
  `location`, and `action`.
- The macOS app exposes Remote Server provider presets for Kimi, Gemini,
  DeepSeek, GLM, and Custom. Preset base URLs are fixed in code; Custom keeps an
  editable OpenAI-compatible base URL for sub2api-style gateways.
- Gemini uses the Google Generative Language `generateContent` REST shape rather
  than OpenAI-compatible `/chat/completions`.
- The macOS app installs the standard AppKit Edit menu so text entry controls
  receive paste, copy, cut, undo, redo, and select-all commands.

## Interfaces

CLI target management:

```bash
melix remote-server list --json
melix remote-server add --remote-server-id sub2api --title sub2api --provider custom --base-url https://example/v1 --model gemini-2.5-flash --api-key "$KEY"
melix remote-server add --remote-server-id gemini --title Gemini --provider gemini --model gemini-2.5-flash --api-key "$KEY"
melix remote-server update --remote-server-id sub2api --model kimi-2.6
melix remote-server remove --remote-server-id sub2api
melix remote-server test --remote-server-id sub2api --model gemini-2.5-flash
```

Direct chat:

```bash
melix chat run --remote-server-id sub2api --model gemini-2.5-flash --message "hello"
```

Direct evaluation:

```bash
melix eval run --remote-server-id sub2api --remote-model gemini-2.5-flash --source-jsonl /Users/ChenYu/Downloads/top200_final.jsonl --scoring-mode event_extraction_weighted_f1 --sample-size 3
```

## Persistence Contract

Visible Remote Server metadata is stored in:

```text
$MELIX_HOME/state/remote-servers.json
```

Remote Server API keys are stored in:

```text
$MELIX_HOME/secrets/remote-server-api-keys.json
```

Visible state contains only `api_key_hint` and `credential_ref`. API keys must
not be copied into normal state, logs, evaluation job parameters, prediction
JSONL, scorer summaries, or exported result payloads.

Remote Server state also stores `provider_preset`. Legacy records without this
field decode as `custom`. Preset resolution is:

- `kimi`: `provider_kind = openai-compatible`,
  `base_url = https://api.kimi.com/coding/v1`
- `deepseek`: `provider_kind = openai-compatible`,
  `base_url = https://api.deepseek.com/v1`
- `glm`: `provider_kind = openai-compatible`,
  `base_url = https://open.bigmodel.cn/api/paas/v4`
- `gemini`: `provider_kind = gemini-generative-language`,
  `base_url = https://generativelanguage.googleapis.com/v1beta`
- `custom`: `provider_kind = openai-compatible`, operator-provided `base_url`

For Gemini, clients construct:

```text
POST <base_url>/models/<remote_model_id>:generateContent?key=<api_key>
```

The model id remains separate from the stored base URL.

## Evaluation Outputs

Event extraction runs write model-specific artifacts under:

```text
<evaluation-jobs-root>/event-extraction/<run-id>/predictions/<model>.jsonl
<evaluation-jobs-root>/event-extraction/<run-id>/predictions/<model>.failures.jsonl
<evaluation-jobs-root>/event-extraction/<run-id>/reports/<model>/event_eval_summary.json
<evaluation-jobs-root>/event-extraction/<run-id>/reports/<model>/event_eval_details.jsonl
```

The scorer aligns events by `dialogue_id + event_index`, excludes `digest`, and
uses exact string set comparison with weights:

- `action = 0.35`
- `actor = 0.30`
- `time = 0.25`
- `location = 0.10`

## Verification

- Remote Server persistence covers secret redaction, credential lookup,
  preserve-on-update, and remove behavior.
- OpenAI-compatible client tests cover non-streaming response parsing and SSE
  streaming deltas.
- Gemini client tests cover `generateContent` URL construction, API key query
  placement, request body mapping, finish reason mapping, and response parsing.
- Control-plane tests cover remote Chat routing and transient remote Evaluation
  forwarding.
- Worker tests cover event digest normalization, weighted F1, failure reporting,
  prediction output, remote event extraction output paths, and Gemini
  `generateContent` extraction.
- macOS app tests cover the standard Edit menu and provider preset draft
  behavior.
