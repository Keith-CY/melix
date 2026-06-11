# Melix Unified Agentic Tool Runtime Contract

## Purpose

This specification governs the OpenSearch-VL alignment direction tracked by
issue #674. Melix must expose one local, replayable agentic tool runtime for:

- supervised fine-tuning data replay
- reinforcement-learning rollout
- benchmark runs
- evaluation runs

The runtime exists so tool schemas, tool execution, observations, failure
classification, replay metadata, and persisted evidence do not fork into
trainer-only, evaluator-only, or benchmark-only conventions.

## Methodology Source

This contract is informed by the OpenSearch-VL recipe, which uses a shared
visual and retrieval tool environment across agentic SFT, RL rollout, and
inference or evaluation. The source methodology includes cold-start agentic SFT,
multi-turn fatal-aware GRPO, and a unified tool set containing visual attention,
layout parsing, retrieval, page visit, image enhancement, and programmatic
compute tools.

Melix does not import the upstream training stack as-is. The Melix contract
keeps local-first Apple Silicon ownership boundaries:

- Swift control plane owns orchestration, request admission, operator-facing
  state, and persisted run routing.
- Python workers own deterministic tool adapter execution, runtime-local
  payload handling, and sample or trajectory evidence construction.
- Repository docs and run evidence remain the source of truth for shipped
  behavior claims.

## Scope

This contract applies to:

- agentic tool schemas exposed to model requests
- tool-call parsing contracts used by text and vision models
- deterministic local tool adapters used by CI and fixture-backed runs
- observation redaction, byte limits, timeout status, and replay metadata
- SFT trace replay from `agentic_tool_trace` training packages
- RL rollout trajectory capture
- benchmark and evaluation sample evidence
- report and export fields that summarize tool-use behavior

This contract does not require:

- network-backed search in CI
- importing OpenSearch-VL's CUDA training infrastructure
- replacing the existing `bench` and `eval` product split
- treating benchmark/evaluation claims as complete without persisted artifacts

## Existing Melix Anchors

Current implementation anchors that future slices must reuse instead of
redefining equivalent contracts:

- `docs/agentic-trajectory-dataset-contract.md`
  - defines the repository-owned `agentic_tool_trace` package, validation, and
    provenance contract for issue #664
- `services/mlx-worker-python/worker/runtime/tool_registry.py`
  - defines `melix.agentic_tool_registry.v1`
  - defines the built-in `melix.agentic_tools.builtin.v1` toolset
  - emits OpenAI function tool schemas and worker `ToolConfig`
- `docs/plans/2026-05-11-opensearch-vl-tool-runtime-foundation.md`
  - records the implemented registry foundation slice for issue #676
- `services/mlx-worker-python/worker/runtime/tool_observation.py`
  - defines `melix.agentic_tool_observation.v1`
  - normalizes redaction, byte limits, timeout metadata, metrics, and replay
    fingerprints
- `docs/plans/2026-05-11-opensearch-vl-tool-observation-contract.md`
  - records the implemented observation contract slice for issue #677
- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
  - accepts `agentic_tool_trace` packages and reports trace quality metrics
- `docs/plans/2026-05-11-opensearch-vl-agentic-foundation.md`
  - records the first implemented data-foundation slice for agentic trace
    package ingestion

## Built-In Tool Set

The v1 Melix built-in tool names are:

| Tool | Kind | Observation Kind | Required Role |
| --- | --- | --- | --- |
| `image_crop` | `vision.image_crop` | `image_region` | crop or inspect a bounded region from a referenced image |
| `layout_parse` | `vision.layout_parse` | `layout_elements` | extract document, page, OCR, or visual layout elements |
| `text_search` | `retrieval.text_search` | `search_results` | search fixture-backed textual evidence |
| `image_search` | `retrieval.image_search` | `image_search_results` | search fixture-backed image evidence |
| `visit` | `browser.visit` | `page_extract` | fetch or read a fixture-backed page/document |
| `local_compute` | `compute.local` | `compute_result` | run deterministic local computation over supplied values |

Additional tools may be added only by extending the registry contract, tests,
and evidence fields in the same change. Ad hoc per-surface tool names are not
allowed.

## Tool Registry Contract

Each tool descriptor must include:

- stable `name`
- human-readable `description`
- machine-readable `tool_kind`
- machine-readable `observation_kind`
- JSON-schema-compatible argument descriptors
- required argument list
- registry `schema_version`
- `toolset_version`
- parser family and parser contract version

The worker-facing registry must be serializable to a deterministic `ToolConfig`
receipt. Any request that selects a subset of tools must preserve request order,
deduplicate repeated names, and fail before execution on unknown names.

## Tool Selection Receipt Contract

Agentic prompt assembly may select a bounded subset of the built-in registry
instead of exposing every tool schema to every local model request. Selection is
advisory and must not remove tools that are marked always available for local
diagnostics or deterministic compute. Semantic retrieval may provide candidate
tool IDs, but unavailable or empty retrieval must degrade to deterministic
keyword matching over the current user turn and recent user-turn context.

The v1 selector receipt is `melix.agentic_tool_selection.v1` and records:

- `toolset_version`
- `selection_mode = vector|keyword|fallback`
- `vector_available`
- `fallback_reason`
- `selected_tools[]` with `tool_id` and source label:
  `always`, `vector`, `keyword`, or `keyword_context`
- `dropped_tool_count`
- `full_schema_bytes`
- `selected_schema_bytes`

Receipts must not include raw prompt text, private context, or tool arguments.
They exist to explain why a schema was included or dropped and to measure prompt
schema overhead. The deterministic agentic runtime records the selector receipt
inside its `melix.agentic_tool_run.v1` registry receipt when a caller provides a
selection input, and the selected registry is the execution allowlist for that
run.

## Observation Contract

Every emitted observation must include:

- `schema_version`
- `tool_name`
- `tool_call_id`
- `observation_kind`
- status: `completed`, `timeout`, or `failed`
- sanitized payload
- metric block
- replay metadata

Payload handling must:

- redact configured terms before persistence
- enforce UTF-8-safe byte limits
- preserve deterministic hashes over sanitized payloads
- record timeout metadata when status is `timeout`
- reject empty observations

### Untrusted Fixture Boundary

Fixture-backed tool arguments, retrieved corpus rows, page extracts, image
captions, layout payloads, crop payloads, and status-control payloads are
untrusted input even when they are loaded from local test fixtures or replay
packages. The deterministic runtime must validate these values before URL
lookup, corpus filtering, document parsing, tool-block parsing, or prompt
assembly. It must not coerce unexpected containers or scalar values into
strings because that can hide prompt-injection payloads inside trusted-looking
tool evidence.

Selected retrieved corpus containers and their rows are part of the same
boundary. A selected text or image corpus must be a JSON list, and each corpus
row must be a JSON object, before adapter filtering or result projection runs.

When an unexpected untrusted value type is encountered, the runtime must fail
closed with a failed observation rather than executing the adapter. The failed
observation payload must include:

- `reason = invalid_untrusted_input_type`
- `source_type`
- `source_id`
- `field`
- `expected_type`
- `actual_type`
- `corrective_action`

The v1 Python worker slice applies this boundary to the deterministic agentic
tool runtime. Later retrieval, skill, memory, workspace, and background-job
entrypoints must reuse the same receipt shape when they introduce their own
source-specific validators.

### Owner Scope Boundary

Retrieved documents, retrieved images, page extracts, layout payloads, crop
payloads, future skill payloads, future memory payloads, and background-job
continuation artifacts must fail closed when their effective owner does not
match the active request or workflow owner. Owner checks run before the segment
is projected into a tool observation, prompt context, tool action, or
continuation chain.

For deterministic fixture-backed agentic tools, callers may provide an expected
owner through fixture context. Retrieved fixture segments that declare a
different `owner_id` must emit a failed observation instead of prompt-visible
content. When owner checks fail, the failed observation payload must include:

- `reason = owner_scope_mismatch`
- `source_type`
- `source_id`
- `expected_owner_id`
- `actual_owner_id`
- `owner_scope_checked = true`
- `privilege`
- `corrective_action`

The v1 deterministic adapter slice applies this boundary to fixture-backed text
search rows, image search rows, pages, layouts, and crops. Broader RAG stores,
skill entrypoints, memory entrypoints, and background-job continuations must
reuse the same receipt shape when they add owner-aware payloads under #1761.

### Prompt Construction Boundary

Retrieved documents, skills, memories, tool observations, media references,
sample questions, expected answers, and model final answers must remain
untrusted data when they are projected into prompt messages. Prompt assembly
must keep those segments out of system and developer instructions unless the
operator has explicitly configured them as trusted instructions.

Prompt snapshots and prompt evidence should record one receipt for each
admitted untrusted segment. The receipt shape is:

- `schema_version = melix.untrusted_context_receipt.v1`
- `segment_id`
- `source_type`
- `source_field`
- `message_role`
- `trust_level = untrusted`
- `policy = data_only`
- `boundary_checked = true`
- `included`
- `owner_scope_checked`
- `reason`
- `corrective_action`

The v1 agentic judge prompt snapshot slice records this receipt for every
sample-derived user-payload field admitted into the judge user message. It does
not change judge prompt wording or scorer behavior.

The v1 control-plane chat prompt assembly slice records the same receipt shape
for non-empty non-system/developer message parts after request shaping and
before `Melix_Worker_V1_GenerateRequest.messages` is sent to the worker.
Receipts are stored in `ExecutionMetadata.ext` as:

- `melix.prompt_context.receipt_schema`
- `melix.prompt_context.receipt_count`
- `melix.prompt_context.receipts_json`

The Python worker completion evidence slice forwards those three request-local
ext values into `Completed.parser_metrics` as:

- `prompt_context_receipt_schema`
- `prompt_context_receipt_count`
- `prompt_context_receipts_json`

The worker treats the receipt JSON as opaque evidence and does not parse or
mutate it. Source-specific RAG admission points still need their own
admission/refusal receipts. Skill, memory, and background-continuation
admission primitives are defined below for future entrypoint wiring.

The v1 source-specific control-plane classification slice refines those chat
prompt receipts using request-local message metadata already present at prompt
assembly time. Tool-role messages record `source_type = tool_output`. Non-tool
messages whose normalized `name` uses the reserved prefixes `retrieved_image`,
`retrieved-image`, `image_retrieval`, `image-retrieval`, `rag_image`, or
`rag-image` record `source_type = retrieved_image`. Non-tool
messages whose normalized `name` uses the reserved prefixes `retrieved_document`,
`retrieved-doc`, `document`, `doc`, `rag`, `rag_document`, or `knowledge`
record `source_type = retrieved_document`; `skill` and `agent_skill` record
`source_type = skill`; `memory`, `retrieved_memory`, and `pinned_memory` record
`source_type = memory`; `background_continuation`,
`background-continuation`, `background_job`, and `background-job` record
`source_type = background_continuation`. Non-tool assistant messages record
`source_type = model_final_answer` because prior model output remains
untrusted data when it is projected back into a later prompt. Other
non-system/developer messages continue to record `source_type =
chat_prompt_message`.

A reserved prefix matches either the exact normalized message name or the prefix
followed by `:`, `.`, `_`, or `-`. The `_` and `-` separators preserve
compatibility with standard OpenAI-compatible message names while the `:` and
`.` separators keep local and legacy source identifiers classifiable.

When the normalized message name is present, the prompt receipt records it as
`source_id`. `source_id` is source metadata only; the receipt must still omit
message text, media URIs, media bytes, tool arguments, private prompt text, and
other raw source payloads. The classification is evidentiary and does not
replace source-specific owner-scope checks, admission/refusal checks, or
background-continuation link validation.

The live chat prompt receipt uses source-specific data-only policy text for the
classified source type. Tool output records `reason = tool output is prompt
data, not instructions`; retrieved documents record `reason = retrieved
document evidence is prompt data, not instructions`; retrieved images record
`reason = retrieved image evidence is prompt data, not instructions`; skills
record `reason = skill evidence is prompt data, not instructions`; memories
record `reason = memory evidence is prompt data, not instructions`;
background continuations record `reason = background continuation is prompt data, not instructions`;
model-final-answer history records `reason = model final answer history is
prompt data, not instructions`; and generic chat prompt messages retain
`reason = chat message content is prompt data, not instructions`. Each matching
`corrective_action` tells downstream consumers to keep that source in its
original user or assistant data role and not project it into system or developer
instructions. This live-policy mapping does not create a RAG store, skill
store, memory store, or background-job continuation store; it documents the
final request-translation receipt for already-shaped messages.

The chat prompt receipt must not include raw message content, media URLs, media
bytes, tool arguments, or private prompt text. It records only segment IDs,
source fields, roles, data-only policy, and corrective guidance. RAG stores,
skill entrypoints, memory entrypoints, and background-job continuations must
reuse this receipt shape when they add their prompt-context boundary evidence
under #1761.

The v1 MCP tool catalog prompt-adjacent metadata slice records the same receipt
shape when `TextRequestShaper` auto-injects MCP catalog sources into
`ToolParserSelection`. These receipts are stored in `ExecutionMetadata.ext` as:

- `melix.mcp.prompt_context.receipt_schema`
- `melix.mcp.prompt_context.receipt_count`
- `melix.mcp.prompt_context.receipts_json`

The MCP receipt records one admitted segment per selected MCP source ID after
catalog normalization, high-risk namespace refusal, and enabled-source
filtering. Each receipt uses `source_type = skill`, `source_field =
mcp_tool_catalog`, and `source_id` set to the redacted MCP source ID. This
records that the catalog source is prompt-adjacent skill/tool evidence and not
trusted instructions. The receipt must not include MCP config paths, tool
namespaces, tool schemas, tool arguments, private prompt text, or raw source
payloads.

The v1 control-plane session-context slice records the same receipt shape when
`RequestCoordinator` resolves an implicit follow-up restore snapshot from
`SessionGraphStore`. These receipts are stored in `ExecutionMetadata.ext` as:

- `melix.session_context.receipt_schema`
- `melix.session_context.receipt_count`
- `melix.session_context.receipts_json`

The session-context receipt uses `source_type = background_continuation`,
`source_field = execution.cache_hints.restore_snapshot_id`, and records the
selected snapshot ID as `source_id`. `owner_scope_checked` is `true` only for
the in-memory session graph lookup that matched the request session and
selected branch before setting the restore snapshot. Caller-supplied explicit
`restore_snapshot_id` values must still emit the same redacted session-context
receipt so the boundary is visible, but they must record
`owner_scope_checked = false` until a future owner-aware snapshot lookup
validates the ID. The receipt must not include raw prompt text, hidden
reasoning text, prior model output, or private prompt bodies.

The v1 Python worker prompt-context primitive is
`worker.runtime.untrusted_context.untrusted_context_receipt`. It constructs the
stable `melix.untrusted_context_receipt.v1` dictionary for both admitted and
refused untrusted user-message segments. Existing agentic judge prompt
snapshots use this helper, and later retrieved-document, skill, memory,
tool-output, and background-continuation admission points must use the same
helper or preserve its exact receipt shape, including the optional `source_id`
field for retrieved segments, when they record prompt-boundary evidence.

The shared Python worker prompt-context admission primitive is
`worker.runtime.prompt_context`. A `PromptContextSegment` represents one
untrusted source field that a caller intends to project into a user-role prompt
payload. `admit_prompt_context_segments` returns the prompt payload fields plus
matching untrusted-context receipts, rejects duplicate source fields before
overwrite, and rejects non-user roles for untrusted context. Receipts contain
source metadata and boundary decisions only; they must not copy the raw segment
value. `refused_prompt_context_receipt` provides the same receipt shape with
`included = false` for source-specific validators that reject malformed,
cross-owner, or otherwise inadmissible segments before prompt assembly.

The v1 prompt-context primitive slice migrates the agentic judge prompt snapshot
receipt generation onto `worker.runtime.prompt_context` without changing
persisted prompt messages, receipt shape, scorer behavior, or judge prompt
wording. Later RAG, skill, memory, chat prompt-assembly, and background
continuation slices should use this primitive when they decide which untrusted
segments are admitted into user-role prompt context.

The source-specific Python worker prompt-context helper is also in
`worker.runtime.prompt_context`. `PromptContextSourceEvidence` and
`admit_prompt_context_source_evidence` provide a common admission path for
retrieved document evidence, retrieved image evidence, skill evidence, memory
evidence, and background-continuation evidence. The helper supplies stable
data-only reason and corrective-action text for each source type, preserves
`source_id` and `owner_scope_checked`, rejects unsupported source types, and
still delegates receipt construction to `PromptContextSegment`. Source-specific
entrypoints should use `refused_source_prompt_context_receipt` when malformed,
cross-owner, or otherwise inadmissible evidence is rejected before prompt
assembly. The helper does not create a skill store, memory store, live RAG
store, or background-job continuation mechanism; it standardizes the receipt
surface those entrypoints must use when they are wired.

The agentic judge prompt snapshot entrypoint must build its admitted receipts
through `admit_prompt_context_segments` and its validator refusal receipts
through `refused_prompt_context_receipt`. This keeps the concrete prompt
snapshot path aligned with the shared admission primitive while preserving the
stable receipt JSON and persisted prompt payload.

The Python worker background-continuation admission primitive is
`worker.runtime.background_continuation.admit_background_continuation`. Future
durable local-job monitors and session follow-up paths must pass already
redacted background-job evidence through this helper before projecting it into
user-role prompt context. The helper records one
`source_type = background_continuation` receipt with `source_field =
background_job` and `source_id` set to the redacted job identifier. Malformed
continuation fields produce `included = false` refusal receipts with `reason =
invalid_background_continuation_field` and no user payload. The helper does not
implement durable job storage, process monitoring, or session resume; it is only
the prompt-context boundary for follow-up data admitted by those later
surfaces.

Concrete local-job, workflow, and continuation entrypoints may override the
default `segment_id`, `source_field`, `reason`, and `corrective_action` when
they need to identify the specific redacted result slot they are admitting. The
default remains `segment_id = <job_id>:background-continuation` and
`source_field = background_job`. Malformed entrypoint-local metadata must fail
closed before prompt admission with the same `invalid_background_continuation_field`
refusal receipt and must not include raw logs, command text, session contents,
or workflow payloads.

The workflow-facing Python worker helper is
`worker.runtime.background_continuation.admit_workflow_continuation_result`.
It is a prompt-boundary primitive for already-redacted workflow continuation
results, not a workflow runner or scheduler. The helper maps the redacted
workflow run ID, and optional workflow node ID, into `source_id =
<workflow_run_id>[:<workflow_node_id>]` and keeps
`source_type = background_continuation`. By default it emits
`segment_id = <source_id>:workflow-continuation`,
`source_field = workflow_result`, and workflow-specific data-only reason and
corrective-action text. Concrete workflow entrypoints may still override
`segment_id`, `source_field`, `reason`, and `corrective_action` through the same
entrypoint-local metadata surface. Malformed workflow run IDs, workflow node
IDs, result payloads, and owner-scope metadata must fail closed with
`included = false`, `reason = invalid_background_continuation_field`, and no
user payload.

The Python worker local-job continuation primitive is
`worker.runtime.local_job_continuation`. It defines a versioned
`melix.local_job_continuation_record.v1` record for durable background local
jobs before runner and monitor side effects are added. The record persists the
job ID, command vector, working directory, log path, exit status, timeout,
originating session ID, follow-up status, follow-up session ID,
`followed_up_at`, and explicit completion evidence paths. Store writes use
atomic JSON replacement plus per-record write locks and revision checks so
concurrent writers fail closed instead of silently overwriting each other. Job
IDs must be cross-platform-safe record filenames. If a lock file belongs to a
dead writer PID, the store may recover it only after acquiring a short-lived
recovery guard, renaming the stale file, and revalidating the lock identity
before deletion. Windows process IDs are treated as active because
`os.kill(pid, 0)` is not a portable liveness probe there. Malformed lock files,
permission-protected active processes, active recovery guards, concurrent lock
reacquisition, and failed lock cleanup all preserve the lock or refuse the write
instead of deleting a possibly active writer lock. If the stale candidate
disappears before its writer PID can be read, the store treats the lock as
already cleared and retries acquisition instead of reporting a blocked write.

Persisted local-job state is advisory. A record marked `completed` is accepted
as final only when a success marker path or artifact path is present on the
record or matching live evidence. A stale `completed` record without completion
evidence must reconcile back to `running` when a matching live session still
shows progress, emitting a `melix.local_job_continuation_receipt.v1` receipt
with `reason = stale_done_revived`. A pending or running record with matching
active live progress must emit `reason = live_session_reused` and
`duplicate_launch_refused = true` so future runners reattach instead of
launching duplicate local work. Completed records without evidence emit
`reason = missing_completion_evidence` and remain blocked until explicit
completion evidence appears.

Callers that are reconciling persisted state must use
`LocalJobContinuationStore.reconcile_record` instead of separately loading,
reconciling, and saving records. The store-backed entrypoint loads the latest
record, applies the side-effect-free reconciliation primitive, persists revived
running state or live completion evidence with the same optimistic revision
guard used by normal writes, and returns `None` when no record exists for the
job ID. If another writer changes the record during reconciliation, the write
must fail closed with the existing `record_revision_mismatch` receipt. The
same store owns follow-up claiming through `LocalJobContinuationStore.claim_followup`.
Claiming first reconciles the latest persisted record with optional live
completion evidence, then marks an evidence-backed completed record
`followup_status = in_progress` with the claiming follow-up session ID. Duplicate
claims must return `reason = followup_already_claimed` without changing the
record. Non-completed records return `reason = followup_not_ready`, and
completed records without success or artifact evidence keep the existing
`missing_completion_evidence` blocker. Claim writes use the record revision
guard so two monitor loops cannot silently enqueue two follow-ups.

The primitive does not start processes, tail logs, inject prompt follow-ups, or
resume workflows. Store-backed local-job monitor or session follow-up callers
that are ready to project a completed job summary into prompt context must call
`LocalJobContinuationStore.claim_followup_prompt_context`. That entrypoint first
computes the same reconciliation and single-claim decision as
`claim_followup`, then admits the already-redacted completion summary through
`admit_background_continuation` with `source_field =
local_job_completion_summary` and `segment_id = <job_id>:local-job-followup`.
Only after prompt-context admission succeeds may it persist the follow-up claim.
Malformed completion summaries or owner-scope metadata must fail closed with a
`background_continuation` refusal receipt, no prompt payload, and no stored
`in_progress` follow-up claim. Store-level blockers such as missing completion
evidence or an already claimed follow-up must not emit prompt-context payloads.

When a local-job follow-up claim succeeds, the
`melix.local_job_continuation_receipt.v1` receipt must also expose the redacted
background-continuation prompt-boundary evidence for that claim:

- `prompt_context_receipt_schema =
  melix.untrusted_context_receipt.v1`
- `prompt_context_receipt_count`
- `prompt_context_receipts`

The local-job claim uses `source_type = background_continuation`,
`source_field = local_job_followup`, and `source_id` set to the redacted job ID.
`owner_scope_checked` remains `false` until a future owner-aware local-job
monitor validates the job/session linkage. The prompt-context receipt must not
copy command vectors, working directories, log paths, session IDs, success
marker paths, artifact paths, raw log output, prompt text, or hidden reasoning
content. Duplicate, blocked, or not-ready claims must not emit a new admitted
prompt-context segment because no follow-up projection has been reserved.

Future local-job monitor, UI, and session follow-up callers that need a concrete
session message projection must use
`worker.runtime.local_job_continuation.project_local_job_session_followup`
instead of manually stitching claim receipts into prompts. The helper delegates
to `LocalJobContinuationStore.claim_followup_prompt_context`, then returns the
store claim, copied claim receipt, copied prompt user payload, copied
untrusted-context receipts, and a `followup_message` shaped as user-role data:
`{"role": "user", "content": <prompt_user_payload>,
"untrusted_context_receipts": <receipts>}`. When the store reports a missing,
duplicate, blocked, or not-ready record, the helper must not create a follow-up
message payload. Malformed completion summaries or owner-scope metadata keep the
existing fail-closed admission behavior and must not persist an `in_progress`
claim. The projection remains side-effect-free: it does not launch local jobs,
tail logs, read artifact contents, infer owner scope, or enqueue a UI/session
request.

The Python worker skill and memory admission primitives are
`worker.runtime.skill_memory_context.admit_skill_context` and
`worker.runtime.skill_memory_context.admit_memory_context`. Future skill,
agent-skill, retrieved-memory, and pinned-memory entrypoints must pass
already-redacted evidence dictionaries through these helpers before projecting
that evidence into user-role prompt context. Each helper records one
`source_type = skill` or `source_type = memory` receipt with `source_field`
matching the source type and `source_id` set to the redacted skill or memory
identifier. Malformed source IDs, payload objects, or owner-scope metadata
produce `included = false` refusal receipts with `reason =
invalid_skill_context_field` or `invalid_memory_context_field` and no user
payload. Concrete entrypoints may pass entrypoint-local `segment_id`,
`source_field`, `reason`, and `corrective_action` values so public receipt
fields remain stable for agent-skill catalogs, skill stores, pinned memories,
or retrieved-memory stores while receipt generation still routes through
`PromptContextSourceEvidence`. Malformed entrypoint receipt metadata fails
closed before prompt assembly with the same refusal reason. These helpers do
not implement skill lookup, memory persistence, retrieval ranking, or
chat/session wiring; they are only the prompt-context boundary for evidence
admitted by those later surfaces.

The Python worker retrieval admission primitives are
`worker.runtime.retrieval_context.admit_retrieved_document_context` and
`worker.runtime.retrieval_context.admit_retrieved_image_context`. Deterministic
text search, image search, and local visit source receipts pass already-redacted
evidence dictionaries through these helpers before projecting that evidence
into tool-observation prompt context. Future live RAG stores, document
retrieval, image retrieval, and local source integration entrypoints must reuse
the same helpers. By default, each helper records one `source_type =
retrieved_document` or `source_type = retrieved_image` receipt with
`source_field` matching the source type and `source_id` set to the redacted
retrieved source identifier. Concrete result-list and visit entrypoints may
provide entrypoint-local `segment_id`, `source_field`, `reason`, and
`corrective_action` values so their public receipt locations remain stable.
Malformed source IDs, payload objects, owner-scope metadata, or entrypoint
receipt fields produce `included = false` refusal receipts with `reason =
invalid_retrieved_document_context_field` or
`invalid_retrieved_image_context_field` and no user payload. These helpers do
not implement retrieval storage, ranking, indexing, ingestion, or chat/session
wiring; they are only the prompt-context boundary for evidence admitted by
those surfaces.

The v1 control-plane rerank document-boundary slice applies the same receipt
schema to the OpenAI-compatible `/v1/rerank` HTTP response. The handler emits
one redacted `source_type = retrieved_document` receipt per candidate document
under `untrusted_context_receipts`, plus
`untrusted_context_receipt_schema = melix.untrusted_context_receipt.v1`. These
receipts identify request-local document indexes and source IDs only; they must
not include candidate document text, query text, prompt bodies, media URIs, or
private source payloads. Because `/v1/rerank` receives caller-supplied
documents directly and does not perform durable retrieval-store lookup in this
slice, those receipts set `owner_scope_checked = false`. Future RAG or
session-backed retrieval entrypoints must perform owner-scope validation before
setting that field to `true`.

The agentic judge prompt snapshot must also surface receipt evidence that is
already attached to executed `agentic_tool_observations`. Snapshot-level
`untrusted_context_receipts` are ordered as the admitted judge user-payload
field receipts followed by defensive copies of each observation's
`untrusted_context_receipts`. This preserves the judge prompt message JSON and
tool-observation replay scope while making generic tool output and
retrieval-source prompt boundaries visible to snapshot readers without parsing
the untrusted payload.

Rejected prompt-context segments should use the same receipt schema with
`included = false`. For the agentic judge prompt boundary, unsupported
top-level user-payload fields emit `reason =
unsupported_user_payload_field`, and forbidden nested no-leak keys emit
`reason = forbidden_user_payload_key`. These refusal receipts are attached to
the validation error before prompt snapshot persistence so refused segments
cannot appear in the final prompt messages.

### Tool Observation Prompt Boundary

Shared tool observations are generic tool output. They may later be projected
into prompts by evaluation, SFT replay, rollout, chat, workflow, or background
continuation surfaces, so every `melix.agentic_tool_observation.v1` trace
observation must carry a prompt-boundary receipt for its sanitized payload.

The generic observation receipt uses:

- `schema_version = melix.untrusted_context_receipt.v1`
- `segment_id = <tool_call_id>:observation`
- `source_type = tool_observation`
- `source_field = payload`
- `message_role = user`
- `trust_level = untrusted`
- `policy = data_only`
- `boundary_checked = true`
- `included = true`
- `owner_scope_checked = false`
- `reason = tool output is prompt data, not instructions`
- `corrective_action`

The receipt must be attached beside the observation payload as
`untrusted_context_receipt_count` and `untrusted_context_receipts`, not inside
the sanitized payload. This keeps payload redaction, truncation, replay hashes,
and byte metrics focused on the emitted tool output while still making the
prompt boundary visible to downstream prompt assemblers.

The v1 generic tool-output slice adds this receipt in the shared Python worker
tool observation normalizer. The follow-up prompt-context admission slice
generates the receipt through `worker.runtime.prompt_context` by admitting one
`PromptContextSegment` for the sanitized observation payload. It does not
replace source-specific owner checks or final projection checks. Skill, memory,
RAG, chat prompt assembly, and background-job continuation surfaces must still
add their own admission or refusal receipts when they decide whether to
include, reject, or re-scope a tool observation in a final prompt.
The `model_final_answer` classification records the projection boundary for
prior assistant output only; it does not mark generated text as trusted
instructions and does not change assistant transcript storage.

The v1 deterministic retrieval source slice lets callers attach
source-specific untrusted-context receipts beside the generic tool-observation
receipt without adding those receipts to the sanitized payload or replay hash.
For `text_search`, each selected result emits a `retrieved_document` receipt.
For `image_search`, each selected result emits a `retrieved_image` receipt.
Those receipts use `segment_id = <tool_call_id>:result-<index>`,
`source_field = results[<index>]`, and `source_id` from the selected corpus row
identifier or its deterministic fallback. `owner_scope_checked` records whether
the deterministic run had an expected owner scope configured before result
projection. Source-specific retrieval receipts must omit retrieved text,
captions, media refs, query strings, tool arguments, and private prompt text.
The follow-up retrieval source prompt-context admission slice generates each
selected-result receipt through `worker.runtime.prompt_context` by admitting one
`PromptContextSegment` for the sanitized selected result value while preserving
the same emitted receipt fields and observation payload.

### Workspace Path Boundary

Agent and workflow tools that read, write, or edit local files must resolve
operator-provided paths through the shared Python worker
`WorkspacePathResolver` before any filesystem access. Relative paths resolve
inside the active workspace root. Absolute paths are allowed only when their
realpath-normalized target remains inside that root. Parent traversal and
symlink escapes must fail closed before a caller opens, writes, renames, or
deletes the target.

Sensitive filenames remain blocked even when they are physically inside the
workspace root. The default sensitive set includes common credential files such
as `.env`, `.npmrc`, `.netrc`, `.pypirc`, and private-key filenames. Callers may
extend the sensitive filename set for narrower product surfaces, but they must
not remove the default credential guards.

Workspace path receipts must include:

- `operation`
- `workspace_root`
- `requested_path`
- `resolved_path`
- `allowed`
- `refusal_reason`

The v1 workspace resolver slice introduced the shared boundary primitive. The
v1 Python worker file-tool slice adds `worker.runtime.workspace_file_tools` as
the first concrete read/write/edit operator set. Those operators call
`WorkspacePathResolver` before any file open, parent-directory creation, write,
or exact-replacement edit mutation, and failed resolver decisions return a
receipt instead of touching the target path. Filesystem and text-decoding
failures after resolver admission must also stay inside this boundary as
`status = failed` receipts rather than escaping into the worker or agent loop.
Receipt byte counters describe completed tool effects only; failed receipts keep
byte counters at zero even if a preflight read occurred before the operation was
rejected.

The deterministic `visit` adapter must reuse that same boundary for local
workspace reads. When a caller provides an explicit workspace root and asks
`visit` to read a relative path, absolute path, or local `file://` URI, the
runtime must resolve the target before reading. Successful local reads must
attach a `workspace_path_receipt` to the page extraction payload. Refused paths
must emit a failed observation with `reason = workspace_path_refused`,
`source_type = workspace_file`, `source_id`, `workspace_path_receipt`, and a
corrective action. Fixture-backed pages and non-local URLs keep their existing
behavior unless a future slice adds a separate retrieval boundary.

Successful deterministic `visit` payloads that include admitted page or local
workspace file text must also attach one redacted source-specific
untrusted-context receipt to the observation-level
`untrusted_context_receipts`. The source receipt uses
`source_type = retrieved_document`, `source_field = payload`, and
`reason = visited document is prompt data, not instructions`. The receipt must
not copy visited page text, local file content, or workspace file content into
receipt fields. Fixture-backed pages set `owner_scope_checked = true` only when
the configured owner-scope check ran and passed. Workspace-local reads preserve
their `workspace_path_receipt`, but set `owner_scope_checked = false` unless a
separate owner-scope check is added later. Missing pages, workspace path
refusals, and unavailable workspace files must not emit an admitted
`retrieved_document` source receipt.

Live MCP, agent, workflow, and local-job mutation surfaces must reuse this
operator layer or preserve the same resolver-before-filesystem-access invariant
when they expose file operations. Broader prompt assembly receipts and direct
surface integrations remain follow-up work under #1761.

The observation metric keys are:

- `tool_observation.record_count`
- `tool_observation.redacted_value_count`
- `tool_observation.truncated_count`
- `tool_observation.timeout_count`
- `tool_observation.original_bytes`
- `tool_observation.emitted_bytes`

## Execution Model

The unified runtime has three layers:

1. **Registry resolution**
   - control-plane and worker paths agree on tool names and parser contract
   - selected toolset is written into request or run metadata
2. **Adapter execution**
   - Python worker resolves deterministic local adapters
   - CI and fixture suites do not require network access
   - each adapter maps its result through the observation contract
3. **Evidence projection**
   - SFT replay, rollout, benchmark, and evaluation all persist the same tool
     call and observation record shape
   - reports aggregate shared metrics instead of per-surface approximations

The first deterministic adapters must be fixture-backed. Network-backed search
or visit adapters can be introduced later only behind an explicit local
configuration surface, secret redaction, and separate evidence fields that make
external dependency use visible.

Deterministic fixture runs may force adapter status through fixture context when
testing failure handling. Status overrides must be available to every built-in
adapter and must still emit normal `melix.agentic_tool_observation.v1` records.
Cancellation is represented as observation status `failed` with
`failure_stage: cancelled` and `cancelled: true` in the sanitized payload,
because the v1 observation status set is intentionally limited to `completed`,
`timeout`, and `failed`.

## Surface Contracts

### SFT Data Replay

`agentic_tool_trace` packages are the replayable training data shape governed by
`docs/agentic-trajectory-dataset-contract.md`. A replay slice must validate that
each tool observation references a prior assistant tool call and must preserve
trace identity, media references, tool schemas, turns, final answer, expected
answer, evidence IDs, reward, fatal stage, and leakage terms.

Required evidence:

- normalized package manifest
- trace quality metrics
- dirty sample reasons for explicit leakage terms
- registry/toolset version used for replay

### RL Rollout

Rollout must call the same adapter layer as evaluation and benchmark. A rollout
trajectory must record:

- prompt/sample identity
- registry receipt
- assistant tool calls
- normalized observations
- fatal stage, if any
- reward components
- replay fingerprint for deterministic reruns

For online GRPO `runtime_generate`, tool-call events emitted by the policy
runtime are candidate-local. The rollout runner must execute each candidate's
tool calls through the shared adapter layer before scoring that candidate, and
the selected policy-update row must reflect the selected candidate's tool
trajectory. Sample-level replay evidence may seed fixture context, but it must
not be reused as the trajectory for every generated candidate.

Online GRPO must also persist candidate-level reward traces as a first-class
artifact. Each generated candidate row must bind the candidate text, score,
reward components, fatal stage, fatal-state mask, raw GRPO advantage, clamped
GRPO advantage, tool-call sequence, observation summary, selected flag, and
replay fingerprint to the same registry and observation contract used by the
selected policy update. The selected candidate row must include the full
selected tool trajectory; non-selected rows may include summaries plus
candidate-local tool metrics unless a later milestone expands full non-selected
observation retention.

Fatal-aware behavior must distinguish:

- valid pre-failure reasoning
- failed tool execution
- timeout
- parser failure
- post-fatal continuation that must not be treated as normal reasoning

Fatal-aware GRPO uses one-sided advantage clamping. Fatal trajectories may keep
zero or negative advantage for penalty accounting, but positive raw advantage is
clamped to `0.0` and marked with
`grpo_advantage_clamp_reason: fatal_state_positive_advantage`.

### Benchmark

Benchmark runs may score latency and throughput for tool-use paths, but they
must not use separate benchmark-only observation records. Any agentic benchmark
metric must be derived from the same records used by replay and evaluation.

Required metrics:

- per-tool call count
- per-tool completed/timeout/failed counts
- per-tool latency milliseconds
- observation emitted bytes
- fatal-stage count
- replay cache hit/miss count when replay caching exists

### Evaluation

Evaluation must route tool execution through the same adapter layer and persist
sample-level evidence. Evaluation samples that use tools must record:

- selected registry/toolset receipt
- tool-call sequence
- observation sequence
- failure or timeout status
- final extracted result
- score and scoring diagnostics

Evaluation claims are valid only when backed by persisted job artifacts, such
as evaluation samples JSONL, run evidence JSON, or report bundles.

### Provider System Prompt Tool-Call Evaluation

Server sessions can act as agent-facing LLM providers. Provider regression
tests must therefore verify not only whether a tool runtime can execute a tool,
but whether the model obeys system instructions and emits parser-compliant tool
calls for an agent.

The repository-owned golden dataset for this contract is:

`tests/eval/tool-call-system-prompts.v1/`

It covers:

- basic instruction following for required tool calls
- JSON-only or exact public text when tools are forbidden
- tool schema and argument fidelity against built-in Melix tool names
- ordered multi-call and unordered parallel-call matching
- date, time, numeric, corpus, media-reference, and optional argument fidelity
- agent-control negative constraints such as forbidden tools and no-tool
  prompts
- missing required user parameters, no-matching-tool refusals, and user-injected
  fake tool-call markup

The scorer must use Melix's production tool-call parser path when extracting
model output. It must hard-match tool names and arguments, validate public text
policy, aggregate parser failure metrics, and run parsed calls through the
deterministic agentic tool runtime unless a case explicitly records that runtime
validation is skipped for a future-tool argument-extraction scenario. Optional
soft judges may score semantic equivalence or refusal quality, but the CI gate
must remain deterministic without network or closed-source model dependencies.

BFCL and ToolBench are useful external calibration suites, but they do not
replace this repository-owned gate. Imported samples must be normalized into
the same case envelope and pinned with conversion evidence before they can be
used for release claims. The normalization importer consumes only local pinned
JSON or JSONL snapshots and records the source benchmark plus source snapshot
id in each generated case.

CI may run fixture responses only. Local model runs, including Hermes-backed
smoke tests, are optional evidence and must write JSON reports with per-case raw
responses, parsed calls, parser metrics, optional judge results, and aggregate
pass rates.

## Executable Child Issue Matrix

The following child issues define the execution path for issue #674. Each
implementation PR must update this spec or a narrower plan before broad code
changes and must include changed-scope verification according to `AGENTS.md`.

| Parent Milestone | Child Issue | File Scope | Required Tests | Required Metrics | Known Gaps |
| --- | --- | --- | --- | --- | --- |
| M1: define registry and observation contracts | #675 Define tool registry and observation contracts | `services/mlx-worker-python/worker/runtime/tool_registry.py`; `services/mlx-worker-python/worker/runtime/tool_observation.py`; training dataset trace validation when observation shape changes; protocol files only if worker-facing receipt schema changes | focused registry and observation unit tests; UTF-8 truncation/redaction tests; SFT trace validation tests when training data changes; `make proto` only if schema changes; `git diff --check` | `agentic_tool_registry.tool_count`; schema bytes; required argument count; observation record count; redacted value count; truncated count; timeout count; original/emitted bytes | adapter execution is M2; benchmark/evaluation/routing is M3 |
| M2: implement deterministic local adapters | #678 Implement deterministic local tool adapters | new or updated `services/mlx-worker-python/worker/runtime/agentic_tools*.py`; fixture roots under `services/mlx-worker-python/fixtures/`; adapter tests under `services/mlx-worker-python/tests/` | focused adapter tests for `text_search`, `image_search`, `visit`, `layout_parse`, `image_crop`, and `local_compute`; no-network fixture tests; timeout/failed status tests; changed-scope coverage | per-tool calls; latency milliseconds; fixture cache hits; emitted bytes; timeout count; failed count; fatal-stage count | real external providers remain out of scope |
| M3: route evaluation and rollout through same tools | #681 Route evaluation and rollout through the same tools | `services/mlx-worker-python/worker/engine/evaluation_core.py`; `services/mlx-worker-python/worker/productization/evaluation_store.py`; `services/mlx-worker-python/worker/productization/run_evidence.py`; `services/mlx-worker-python/worker/model_ops/rl_alignment_training.py`; Swift export bridge files only if exported schema changes | focused evaluation tests with fixture-backed tool calls; store/export tests; report evidence tests; rollout fixture tests; fatal-aware trajectory tests; persisted artifact smoke when behavior changes; changed-scope coverage | tool-call count per sample; observation count; timeout/failed counts; scoring latency; emitted bytes; trajectory count; tool turns per trajectory; reward component means | online GRPO optimization remains separate from the local evidence harness |

## Verification Gates

Every behavior-changing PR under this contract must report:

- governing spec or plan path
- changed file scope
- focused tests and outcomes
- changed-scope coverage, or a precise `N/A` reason for documentation-only
  changes
- metrics report for the changed scope
- persisted benchmark/evaluation artifacts whenever benchmark/evaluation
  behavior is claimed
- known gaps and deferred work

Documentation-only PRs under this contract may report metrics as:

```text
N/A: documentation-only contract update; no executable runtime path changed.
```

## Current Status

As of PR #875, Melix has shipped the first executable issue #674 slice:

- PR #857 added the worker-owned built-in registry contract and deterministic
  `ToolConfig` receipts.
- PR #860 added the shared observation contract with redaction, byte-limit,
  timeout, failure, and replay metadata.
- PR #875 added the deterministic local adapter runtime for all six built-in
  tools and reused it across SFT `agentic_tool_trace` replay, benchmark request
  rows, evaluation sample JSONL artifacts, report aggregation, and RL alignment
  trace rows.

The issue #674 closure evidence is therefore:

| Requirement | Evidence |
| --- | --- |
| Canonical Melix plan or spec exists | This spec and `docs/plans/2026-05-12-unified-agentic-tool-runtime-execution.md` govern the shipped slice. |
| Milestone 1 has executable scope, tests, metrics, and gaps | Issue #675 records the registry/observation file scope, focused tests, metrics, and known gaps; PRs #857 and #860 implemented the contracts. |
| Milestone 2 has executable scope, tests, metrics, and gaps | Issue #678 records the deterministic adapter file scope, focused tests, metrics, and known gaps; PR #875 implemented fixture-backed adapters for `image_crop`, `layout_parse`, `text_search`, `image_search`, `visit`, and `local_compute`. |
| Milestone 3 has executable scope, tests, metrics, and gaps | Issue #681 records evaluation, benchmark, report, and rollout routing scope; PR #875 persisted shared tool evidence and metrics in those paths. |
| Behavior changes report local verification and changed-scope coverage | PR #875 reported focused pytest commands, compile checks, PR evidence validation, changed-scope coverage of 97 percent for the runtime slice, and 100 percent for the follow-up performance-probe fix. |
| Benchmark and evaluation claims are artifact-backed | PR #875 persisted tool registry receipts, tool calls, observations, and `agentic_tool.*` metrics in benchmark and evaluation JSONL payloads and aggregated them in the benchmark/evaluation report path. |

The remaining known gaps are intentionally outside the issue #674 deterministic
local runtime closure: network-backed search or visit providers, unsafe
arbitrary Python execution, importing upstream CUDA training infrastructure, and
online GRPO optimization beyond the local evidence harness.
