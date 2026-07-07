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

Profile proof and admission receipts should also appear in effective config and
diagnostics surfaces when profile admission was evaluated:

- `requested_profile`
- `effective_profile`
- `profile_mode`
- `proof_matrix_id`
- `verification_status`
- `profile_admission_status`
- `fallback_reason`
- `recovery_hint`

The default `balanced` profile is a baseline serving policy and does not require
a proof row. Optimized or non-baseline profiles require a passing proof row
before Melix admits the profile for serving. If the proof row is missing or did
not pass, diagnostics should report `profile_admission_status` as
`experimental_unverified` or `refused`, keep the effective profile at a safe
baseline when a fallback is used, and include a recovery hint that points the
operator to a passing proof matrix row.

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

When upstream serving code has evaluated readiness or dependency policy,
`effective-config.json` should also include a `serving_readiness` receipt. This
receipt is diagnostics-only: it records facts already known to the serving path
and must not trigger model discovery, health polling, package imports, or
dependency checks during bundle writing.

`serving_readiness` fields:

- `requested_model_id` — operator-requested model identity, alias, or handle.
- `effective_model_id` — backend/runtime identity selected for serving.
- `identity_source` — where the effective identity came from, such as
  `explicit_request`, `cached_catalog`, `backend_health`, or `fallback`.
- `budget_source` — where the serving token or profile budget came from, such
  as `explicit_request`, `profile_default`, or `runtime_default`.
- `health_ready_at` — ISO-8601 timestamp for the first ready health state, or an
  empty string when the session was not ready when the bundle was written.
- `progress_source` — source of readiness/progress truth, such as
  `backend_health`, `cached_status`, or `not_ready`.
- `dependency_policy_status` — dependency policy classification, such as
  `allowed`, `blocked`, or `unknown`.

Diagnostics writers may derive `serving_readiness` from namespaced metadata
when all of these keys are present:

- `melix.serving.readiness.requested_model_id`
- `melix.serving.readiness.effective_model_id`
- `melix.serving.readiness.identity_source`
- `melix.serving.readiness.budget_source`
- `melix.serving.readiness.health_ready_at`
- `melix.serving.readiness.progress_source`
- `melix.serving.readiness.dependency_policy_status`

If any required readiness metadata key is missing, the writer leaves the
original metadata in place and does not synthesize a partial top-level
`serving_readiness` receipt.

When upstream serving code has evaluated the model capability and acceleration
admission contract, `effective-config.json` should also include a
`serving_capability` receipt. This receipt is diagnostics-only: it records
already-resolved admission facts and must not trigger model discovery, optional
dependency imports, health polling, model prefetch, or media route probing
during bundle writing.

`serving_capability` fields:

- `schema_version` - `melix.serving_capability_receipt.v1`.
- `capabilities` - supported serving capabilities, such as `generate_text` or
  `generate_multimodal`.
- `input_modalities` - request input modalities admitted by the current
  resolved contract.
- `output_modalities` - output modalities exposed by the current resolved
  contract.
- `acceleration_profile` - selected serving acceleration profile.
- `requested_mode` - operator-requested acceleration mode.
- `resolved_mode` - effective acceleration mode after capability admission.
- `optional_dependency_source` - whether optional runtime dependencies were not
  required, already available, or refused before dispatch.
- `unsupported_reason` - typed refusal reason, or `none`.
- `ignored_flags` - unsupported or intentionally ignored flags surfaced to the
  operator.
- `fallback_policy` - fallback behavior such as `fail_closed` or
  `observable_fallback`.

Diagnostics writers may derive `serving_capability` from namespaced metadata
when all of these keys are present:

- `melix.serving.capability.schema_version`
- `melix.serving.capability.capabilities`
- `melix.serving.capability.input_modalities`
- `melix.serving.capability.output_modalities`
- `melix.serving.capability.acceleration_profile`
- `melix.serving.capability.requested_mode`
- `melix.serving.capability.resolved_mode`
- `melix.serving.capability.optional_dependency_source`
- `melix.serving.capability.unsupported_reason`
- `melix.serving.capability.ignored_flags`
- `melix.serving.capability.fallback_policy`

The `capabilities`, `input_modalities`, `output_modalities`, and
`ignored_flags` metadata values are comma-separated lists. Empty list items are
ignored; an empty `ignored_flags` value records an empty list. If any required
capability metadata key is missing, the writer leaves the original metadata in
place and does not synthesize a partial top-level `serving_capability` receipt.

The control-plane profile preflight path emits these metadata keys after model
capability and acceleration admission have already been resolved. The emitted
receipt uses model catalog task/modality metadata, the acceleration capability
receipt, and the serving profile admission receipt. For metadata-only
preflight rows, `optional_dependency_source` is `not_required`; rejected
explicit acceleration flags use `fallback_policy=fail_closed`, while admitted
requests use `fallback_policy=observable_fallback`. Bundle writing still must
not perform its own model discovery or optional dependency probes.

For this emitter, `ignored_flags` can include `draft_model_id` when a speculative
draft is missing or refused, `acceleration_mode` when the requested mode or
acceleration capability is unsupported, and `acceleration_profile` when profile
admission is refused after acceleration capability admission succeeds.

When upstream serving code has normalized low-level acceleration fields into one
typed config contract, `effective-config.json` should also include a
`serving_acceleration_config` receipt. This receipt is diagnostics-only: it
records the already-resolved control-plane parser and admission result and must
not start an acceleration controller, probe optional runtimes, load a sidecar,
or alter fallback behavior during bundle writing.

`serving_acceleration_config` fields:

- `schema_version` - `melix.resolved_acceleration_config.v1`.
- `method` - effective acceleration method, such as `baseline` or
  `speculative_decode`.
- `requested_method` - requested method after compatibility normalization.
- `sidecar_model` - resolved draft or companion model id, or an empty string.
- `num_speculative_tokens` - resolved speculative token count.
- `profile` - serving acceleration profile tied to the resolved config.
- `conflicting_flags` - low-level flags or overrides rejected, suppressed, or
  ignored during config resolution.
- `controller_scope` - `request` for request-scoped speculative controllers or
  `none` when no controller is active.
- `disabled_reason` - typed reason for a disabled or refused acceleration path,
  or `none`.

Diagnostics writers may derive `serving_acceleration_config` from namespaced
metadata when all of these keys are present:

- `melix.serving.acceleration_config.schema_version`
- `melix.serving.acceleration_config.method`
- `melix.serving.acceleration_config.requested_method`
- `melix.serving.acceleration_config.sidecar_model`
- `melix.serving.acceleration_config.num_speculative_tokens`
- `melix.serving.acceleration_config.profile`
- `melix.serving.acceleration_config.conflicting_flags`
- `melix.serving.acceleration_config.controller_scope`
- `melix.serving.acceleration_config.disabled_reason`

The `conflicting_flags` metadata value is a comma-separated list. Empty list
items are ignored. `num_speculative_tokens` must be a decimal integer. If any
required key is missing or the token count is invalid, the writer leaves the
original metadata in place and does not synthesize a partial top-level
`serving_acceleration_config` receipt.

When upstream serving admission has evaluated dry-run context and batch memory
fit before worker load or decode, `effective-config.json` should also include a
`serving_memory_admission` receipt. This receipt is diagnostics-only: it records
the already-resolved admission result and must not probe memory, load a model,
start a worker, or change runtime fallback behavior during bundle writing.

`serving_memory_admission` fields:

- `schema_version` - `melix.serving_memory_admission.v1`.
- `requested_context` - caller or model requested serving context length.
- `effective_context` - context length admitted for the worker request.
- `requested_batch` - requested serving batch or concurrency value.
- `effective_batch` - batch value admitted for the worker request.
- `memory_headroom_bytes` - host-memory headroom reserved by admission.
- `estimated_active_bytes` - estimated active serving footprint after
  admission.
- `memory_telemetry_source` - `detected` when upstream admission had a detected
  memory value, or `unknown` when it used a conservative default.
- `admission_reason` - typed reason for the effective context and batch choice.
- `fits_memory` - whether the admitted estimate fits the available memory model.

Current control-plane admission first reads upstream model settings metadata for
a detected-memory value such as `melix.serving.memory.available_bytes`,
`melix.serving.memory.detected_memory_bytes`, or
`melix.device.memory_total_bytes`. Production `ControlPlaneService` and
bootstrap construction paths fall back to `ProcessInfo.processInfo.physicalMemory`
when those model metadata keys are absent, so production serving requests can
emit `memory_telemetry_source=detected` without requiring catalog discovery to
pre-populate memory metadata. Tests and custom `RequestCoordinator` construction
can inject no memory supplier, in which case diagnostics legitimately show
`unknown` telemetry and no memory-based step-down.

For OpenAI-compatible text requests, the control-plane gateway derives the
request-side serving context from the same prompt-budget inputs used for
admission. It writes `melix.gateway.context_length` and
`melix.gateway.requested_context` as the bounded estimate
`min(model_context_window, prompt_tokens_estimated + output_cap_tokens + slack)`.
The output cap remains only an output cap; it is not treated as the context
window. Additional provenance metadata includes
`melix.gateway.context_source`, `melix.gateway.context_window_tokens`,
`melix.gateway.output_cap_tokens`, `melix.gateway.prompt_tokens_estimated`,
`melix.gateway.prompt_tokens_estimate_source`, and
`melix.gateway.prompt_tokens_estimate_slack`. `RequestCoordinator` consumes the
context keys as serving-admission input, then emits the
`melix.serving.memory_admission.*` audit namespace below.

Diagnostics writers may derive `serving_memory_admission` from namespaced
metadata when all of these keys are present:

- `melix.serving.memory_admission.schema_version`
- `melix.serving.memory_admission.requested_context`
- `melix.serving.memory_admission.effective_context`
- `melix.serving.memory_admission.requested_batch`
- `melix.serving.memory_admission.effective_batch`
- `melix.serving.memory_admission.memory_headroom_bytes`
- `melix.serving.memory_admission.estimated_active_bytes`
- `melix.serving.memory_admission.memory_telemetry_source`
- `melix.serving.memory_admission.admission_reason`
- `melix.serving.memory_admission.fits_memory`

The integer metadata values must be decimal, non-negative integers. The
`fits_memory` metadata value must be a boolean string. If any required key is
missing or invalid, the writer leaves the original metadata in place and does
not synthesize a partial top-level `serving_memory_admission` receipt.

When a proxy, workspace-ingest, or worker path has already evaluated network
fetch safety, `effective-config.json` may include a `network_fetch_policy`
receipt and `privacy_audit_counters`. These receipts are diagnostics-only:
bundle writing must not resolve hostnames, follow redirects, open sockets,
probe URLs, inspect source content, or rerun privacy detectors.

`network_fetch_policy` uses schema version
`melix.network_fetch_policy_receipt.v1` and records:

- `surface` - emitting surface, such as `local_proxy_external_media` or
  `workspace_ingest`.
- `route_scope` - route or operation scope for the decision.
- `action` - `passed` or `blocked`.
- `url_class` - classified target, such as `public`, `loopback`,
  `link_local`, `private`, `local`, or `invalid`.
- `url_scheme` - normalized URL scheme or `path` for local path inputs.
- `host_class` - classified host before any caller-provided resolved IP.
- `resolved_ip` - public resolved IP when safe to expose, or a redaction marker
  for private-network targets.
- `resolved_ip_class` - classified caller-provided resolved IP.
- `redirect_hops_checked` - number of redirect hops already evaluated by the
  caller.
- `blocked_reason` - typed refusal reason, or an empty string for passed
  decisions.
- `redacted_url` - URL summary with userinfo, path detail, query, and fragment
  removed.
- `raw_url_included` - always false for exported Melix diagnostics.
- `fetch_attempted` - whether the emitting path attempted a network fetch.

Diagnostics writers may derive `network_fetch_policy` from namespaced metadata
when all of these keys are present:

- `melix.network_fetch.policy.surface`
- `melix.network_fetch.policy.route_scope`
- `melix.network_fetch.policy.action`
- `melix.network_fetch.policy.url_class`
- `melix.network_fetch.policy.url_scheme`
- `melix.network_fetch.policy.host_class`
- `melix.network_fetch.policy.redirect_hops_checked`
- `melix.network_fetch.policy.blocked_reason`
- `melix.network_fetch.policy.redacted_url`
- `melix.network_fetch.policy.raw_url_included`
- `melix.network_fetch.policy.fetch_attempted`

Optional metadata keys:

- `melix.network_fetch.policy.schema_version`
- `melix.network_fetch.policy.resolved_ip`
- `melix.network_fetch.policy.resolved_ip_class`

If any required network-fetch metadata key is missing, the writer leaves the
original metadata in place and does not synthesize a partial top-level receipt.

`privacy_audit_counters` is a list of `melix.privacy_audit_counter.v1`
objects. Each counter records:

- `surface`
- `route_scope`
- `blocked_count`
- `redacted_count`
- `passed_count`
- `raw_sensitive_span_count`

Diagnostics writers may derive one counter from namespaced metadata when all of
these keys are present:

- `melix.privacy.audit.surface`
- `melix.privacy.audit.route_scope`
- `melix.privacy.audit.blocked_count`
- `melix.privacy.audit.redacted_count`
- `melix.privacy.audit.passed_count`
- `melix.privacy.audit.raw_sensitive_span_count`

Optional metadata key:

- `melix.privacy.audit.schema_version`

When a caller has already evaluated local privacy detection policy, diagnostics
may also include `privacy_detector_receipts`. Bundle writing must not scan
prompts, completions, documents, artifacts, or trace payloads to create these
receipts. The caller must attach a complete redacted receipt before diagnostics
serialization.

`privacy_detector_receipts` is a list of
`melix.privacy_detector_receipt.v1` objects. Each receipt records:

- `surface`
- `route_scope`
- `detector_id`
- `policy_id`
- `policy_mode`
- `action` - `passed`, `detected`, `redacted`, or `blocked`
- `categories` - detected category names, not matched values
- `match_count`
- `redacted_span_count`
- `blocked_reason`
- `confidence_source`
- `raw_sensitive_span_count`
- `raw_text_included`

Diagnostics writers may derive one detector receipt from namespaced metadata
when all of these keys are present:

- `melix.privacy.detector.surface`
- `melix.privacy.detector.route_scope`
- `melix.privacy.detector.detector_id`
- `melix.privacy.detector.policy_id`
- `melix.privacy.detector.policy_mode`
- `melix.privacy.detector.action`
- `melix.privacy.detector.categories`
- `melix.privacy.detector.match_count`
- `melix.privacy.detector.redacted_span_count`
- `melix.privacy.detector.blocked_reason`
- `melix.privacy.detector.confidence_source`
- `melix.privacy.detector.raw_sensitive_span_count`
- `melix.privacy.detector.raw_text_included`

Optional metadata key:

- `melix.privacy.detector.schema_version`

Detector receipt derivation is rejected when `raw_text_included` is true or
`raw_sensitive_span_count` is greater than zero. Exported receipts must include
only category/count evidence, never raw sensitive spans or matched snippets.

Local proxy text privacy detection is explicitly opt-in. Set
`MELIX_PRIVACY_DETECTOR_MODE=detect` to scan local proxy text request message
parts before worker dispatch and attach sanitized detector receipt metadata
without changing the worker request. Matched `detect` receipts use
`action=detected`, `redacted_span_count=0`, `raw_text_included=false`, and a
passed privacy audit counter because model-visible content was allowed through
unchanged. Set `MELIX_PRIVACY_DETECTOR_MODE=redact` to replace matched spans
with stable placeholders before worker dispatch and attach the detector receipt
plus a `melix.privacy_audit_counter.v1` counter to worker request metadata. Set
`MELIX_PRIVACY_DETECTOR_MODE=block` to reject matched local proxy text requests
before worker dispatch with a sanitized `privacy_policy_blocked` error
envelope. When the setting is unset, empty, `off`, `disabled`, or any
unsupported value, the detector is not run and local proxy text request behavior
is unchanged.

The local proxy detector uses `surface = local_proxy_text_request` and route
scopes such as `chat_completions`, `completions`, `responses`, and `messages`.
The redacted placeholders are category-level values such as
`[REDACTED_EMAIL]` and `[REDACTED_SECRET]`; detector metadata must still omit
raw matched values and raw prompt snippets. This opt-in slice covers text
message parts only. It does not scan diagnostics bundle content, mutate user
files, inspect workspace documents, or run model-backed entity detection.

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
- `melix.acceleration.profile.requested_profile`
- `melix.acceleration.profile.effective_profile`
- `melix.acceleration.profile.profile_mode`
- `melix.acceleration.profile.proof_matrix_id`
- `melix.acceleration.profile.verification_status`
- `melix.acceleration.profile.profile_admission_status`
- `melix.acceleration.profile.fallback_reason`
- `melix.acceleration.profile.recovery_hint`

## Research Fetch Budget Receipts

Deep-research and web-enabled source tools should emit
`melix.research_fetch_budget_receipt.v1` receipts before any fetched source
content becomes model-visible. These receipts are a byte-budget and cache-key
contract only; they do not perform DNS, redirect, SSRF, or private-network
admission. Real URL dereferencing must still pass through the network fetch
policy layer described by #2188 before bytes are streamed into a research
fetch-budget helper.

Receipts use these status values:

| Status | Meaning |
| --- | --- |
| `ok` | The source fit inside the effective byte budget and can be used as complete fetched evidence. |
| `truncated` | Text content was soft-truncated at the effective byte budget and includes a model-visible partial-content notice. |
| `blocked` | The helper returned no model-visible source content because the declared body exceeded the hard ceiling or a binary/PDF source would have been truncated. |

Expected receipt fields include:

- `source_id`
- `source_url_hash`
- `requested_max_bytes`
- `default_max_bytes`
- `effective_max_bytes`
- `hard_max_bytes`
- `fetched_bytes`
- `declared_total_bytes`
- `truncated`
- `status`
- `blocked_reason`
- `content_type`
- `partial_content_notice`
- `refetch_hint`
- `cache_key`
- `raw_url_included`

`cache_key` must include the effective byte budget and truncation state so a
partial source cannot masquerade as a complete source. Receipts and diagnostics
must not include raw URLs, query strings, credentials, or raw fetched content.

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
- baseline and accelerated resolved acceleration configs when upstream provided
  `serving_acceleration_config` receipts
- acceleration admission status
- fallback reason
- tier stability status
- prefill and decode phase rows

The writer rejects comparisons when the baseline and accelerated runs disagree
on prompt protocol, prompt digest, prompt template digest, model id, task kind,
or generation config. It also rejects non-greedy sampler settings because
deterministic sampling is required before the artifact can support a performance
claim.

When present, the comparison artifact writes each run's
`serving_acceleration_config` receipt under
`runs.<baseline|accelerated>.serving_acceleration_config` and mirrors both
receipts under `methodology.acceleration_configs`. Missing receipts serialize as
empty objects; the comparison writer must not synthesize acceleration configs or
probe runtime state while writing evidence.

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
