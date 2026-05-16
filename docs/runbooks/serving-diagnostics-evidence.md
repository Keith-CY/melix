# Serving Diagnostics Evidence

This runbook defines the operator workflow for Melix serving diagnostics bundles
and baseline-vs-accelerated evidence artifacts.

## When To Use Each Mode

Use a lightweight serving diagnostics bundle when debugging a concrete request:

- unexpected finish reason
- slow first token
- decode throughput drop
- cache restore or fallback ambiguity
- memory-pressure investigation

Use a baseline-vs-accelerated comparison artifact only when supporting a
performance claim. Claim-supporting evidence must use the same prompt protocol,
same prompt digest, same model, same task kind, same generation config, and
greedy deterministic sampling for both runs.

Use `MELIX_PROBE_MODE=debug` when a local operator explicitly wants detailed
debug artifacts. Use `MELIX_PROBE_MODE=evidence` for benchmark, evaluation,
comparison, and release evidence. Use `minimal` or `off` for packaged serving
paths where status surfaces may reuse already-computed counters but must not
start heavyweight samplers or detailed trace capture. Missing or empty
`MELIX_PROBE_MODE` resolves to `minimal`; set `MELIX_PROBE_MODE=off` only for an
explicit opt-out from lightweight health telemetry. A diagnostics
`fallback_applied` field of `true` means Melix received a non-empty unrecognized
mode string and substituted `minimal`.

Do not use debug-only diagnostics bundles as public performance claims. They are
for reproducing runtime shape and request events, not for leaderboard-style
comparisons.

## Serving Acceleration Profiles

Serving acceleration profiles are stable operator-facing intents that resolve
before lower-level serving overrides. Use them when creating or updating a
server session so reports, diagnostics, and benchmark artifacts can state the
chosen serving intent instead of only listing individual knobs.

Initial profiles:

| Profile | Intent | Resolved defaults |
| --- | --- | --- |
| `balanced` | Default local serving with moderate batching. | baseline acceleration, concurrent processing enabled, max concurrent requests `4`, prefill batch size `2`, completion batch size `2`, no draft model, `0` draft tokens |
| `throughput` | Throughput-first serving when a draft model is supplied. | speculative decode, concurrent processing enabled, max concurrent requests `8`, prefill batch size `4`, completion batch size `4`, `6` draft tokens, draft model supplied by operator override |
| `low-memory` | Conservative serving for constrained memory. | baseline acceleration, concurrent processing disabled, max concurrent requests `1`, prefill batch size `1`, completion batch size `1`, no draft model, `0` draft tokens |
| `long-session` | Repeated-session serving with bounded batching. | baseline acceleration, concurrent processing enabled, max concurrent requests `2`, prefill batch size `2`, completion batch size `1`, no draft model, `0` draft tokens |

Examples:

```bash
melix server session create \
  --title "Qwen low-memory" \
  --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit \
  --acceleration-profile low-memory \
  --json

melix server session update \
  --server-session-id server-session-qwen \
  --acceleration-profile throughput \
  --draft-model-id z-lab/Qwen3.5-27B-DFlash \
  --json
```

Manual flags remain valid and override the resolved profile defaults. For
example, `--acceleration-profile throughput --num-draft-tokens 4` keeps the
throughput batching defaults while using `4` draft tokens. A throughput profile
without a draft model is not enough to activate speculative serving; provide
`--draft-model-id` or explicitly override the acceleration mode back to
`baseline`.

Serving state and evidence should record both the selected profile and resolved
settings. In diagnostics and benchmark artifacts, prefer these keys when
available:

- `acceleration_profile`
- `acceleration_profile_id`
- `melix.gateway.acceleration_profile`

## Bundle Layout

Serving diagnostics bundles are written under:

```text
serving-diagnostics/<bundle_id>/
  manifest.json
  effective-config.json
  request-summary.json
  events.jsonl
```

`manifest.json` records:

- schema version
- bundle id
- diagnostics mode
- invocation metadata
- model references
- request id
- task kind
- model id
- runtime kind
- acceleration mode
- event count
- dropped event count
- artifact paths

`effective-config.json` records the effective runtime and request config after
defaults, admission, and runtime-specific resolution.

`request-summary.json` records stable request-level fields:

- request id
- task kind
- model id
- runtime kind
- acceleration mode
- prompt protocol id
- prompt digest
- prompt template digest
- generation config
- status
- finish reason
- prompt and completion token counts
- prefill chunk size
- prefill and decode duration
- `prompt_tps`
- `generation_tps`
- `prefill_tokens_per_second`
- cache hit, miss, restored, and computed token counts
- memory used, total, and peak bytes

`events.jsonl` records phase events. Prefill must appear as a first-class phase
when a request reaches prefill. Event attributes should stay small and must not
include full prompts, full responses, credentials, or operator secrets.

Serving diagnostics event queues are bounded. When the queue reaches its
capacity, the oldest retained debug event is dropped and new request-critical
work continues. `manifest.json` records `event_count` and
`dropped_event_count`, so operators can tell whether a debug bundle is complete
enough for diagnosis. Dropped debug events do not invalidate separate
evidence-mode benchmark or evaluation artifacts.

## Capability Receipts

Model discovery surfaces expose `capability_receipt` for every model returned
by `/api/capabilities` and `melix capabilities --json`. The receipt is the
operator-facing source of truth for task support, requested and resolved
acceleration mode, valid draft model IDs, speculative-head readiness, typed
unsupported reasons, provenance, and recovery hints. Do not infer acceleration
support from model names, aliases, or route kinds when a receipt is present.

Control-plane request admission validates non-baseline acceleration against the
model receipt before worker dispatch. Unsupported requests fail closed with an
`unsupported_acceleration` error code and an `unsupported_reason` such as
`unsupported_mode`, `missing_draft_model`, `draft_model_not_allowed`,
`target_disabled`, `drafter_disabled`, `metadata_inconsistent`, or
`runtime_unavailable`. Accepted worker requests copy receipt-derived audit
metadata into execution ext fields:

- `melix.capability.receipt_schema`
- `melix.acceleration.requested_acceleration_mode`
- `melix.acceleration.resolved_acceleration_mode`
- `melix.acceleration.supported_modes`
- `melix.acceleration.target_capability`
- `melix.acceleration.drafter_capability`
- `melix.acceleration.valid_draft_model_ids`
- `melix.acceleration.unsupported_reason`
- `melix.acceleration.state`
- `melix.acceleration.recovery_hint`

## Lightweight Status Diagnostics

`ListLoadedModels` exposes per-loaded-model throughput counters with the same
field names as request diagnostics:

- `prompt_tps`
- `generation_tps`

Every loaded model summary must include both fields. When the runtime has not
reported counters yet, each field serializes as the float value `0.0`. Text and
multimodal generation runtimes should update these counters from already
computed runtime events; status polling must not trigger heavyweight tracing or
extra token accounting.

## Baseline-Vs-Accelerated Evidence

Baseline comparison artifacts are written as:

```text
serving-diagnostics/<comparison_id>/baseline-vs-accelerated.json
```

The comparison artifact records:

- prompt protocol id
- prompt digest
- model id
- task kind
- effective temperature
- effective top-p
- effective top-k
- greedy sampler status
- acceleration admission status
- fallback reason
- tier stability status
- prefill and decode phase rows

The writer rejects comparisons when the baseline and accelerated runs disagree
on prompt protocol, prompt digest, prompt template digest, model id, task kind,
or generation config. It also rejects non-greedy sampler settings because
deterministic sampling is required before the artifact can support a performance
claim.

## Prefill Override Validation

Prefill chunk size overrides must be positive integers. Invalid overrides must
be rejected before starting a diagnostics session so request artifacts do not
mix runtime failures with malformed operator configuration.

Examples of invalid values:

- `0`
- negative integers
- non-integer strings
- missing values when a prefill override was explicitly requested

## Minimal Python Usage

```python
from pathlib import Path

from worker.productization.serving_diagnostics import (
    ServingDiagnosticsEvent,
    ServingDiagnosticsRequestSummary,
    write_serving_diagnostics_bundle,
)

summary = ServingDiagnosticsRequestSummary(
    request_id="req-1",
    task_kind="text-generation",
    model_id="melix-dev-text",
    runtime_kind="mlx-text",
    acceleration_mode="baseline",
    prompt_protocol_id="chat.completions.v1",
    prompt_digest="sha256:...",
    prompt_template_digest="sha256:...",
    generation_config={"temperature": 0.0, "top_p": 1.0, "top_k": 1},
    status="completed",
    finish_reason="stop",
    prefill_chunk_size=128,
    prefill_ms=12.0,
    decode_ms=30.0,
)

write_serving_diagnostics_bundle(
    output_root=Path(".runtime/evidence"),
    bundle_id="req-1-debug",
    invocation={"command": "melix serve --diagnostics req-1-debug"},
    effective_config={"runtime": {"mode": "baseline"}},
    model_refs={"model_id": "melix-dev-text"},
    request_summary=summary,
    events=(
        ServingDiagnosticsEvent(
            request_id="req-1",
            phase="prefill",
            event_index=0,
            status="completed",
            duration_ms=12.0,
            attributes={"prefill_chunk_size": 128},
        ),
    ),
    diagnostics_mode="debug",
)
```

## Disabling Optional Debug Probes

To disable optional debug diagnostics without breaking benchmark or evaluation
evidence, unset `MELIX_PROBE_MODE` or set it to `minimal` for serving. Keep
benchmark, evaluation, report, and release commands on `evidence` mode when the
output is used for claims. If sampled or debug mode causes local overhead,
disable only that operator session; do not remove `run-evidence.json`,
`probe_timeline`, or `telemetry_summary` from evidence-mode runs.

## Verification

Run the focused diagnostics artifact tests after changing this artifact
contract:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_CACHE_DIR="$PWD/.uv-cache" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py
```
