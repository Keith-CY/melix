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
mutate it. Source-specific RAG, skill, memory, and background-continuation
admission points still need their own admission/refusal receipts.

The chat prompt receipt must not include raw message content, media URLs, media
bytes, tool arguments, or private prompt text. It records only segment IDs,
source fields, roles, data-only policy, and corrective guidance. RAG stores,
skill entrypoints, memory entrypoints, and background-job continuations must
reuse this receipt shape when they add their prompt-context boundary evidence
under #1761.

The v1 Python worker prompt-context primitive is
`worker.runtime.untrusted_context.untrusted_context_receipt`. It constructs the
stable `melix.untrusted_context_receipt.v1` dictionary for both admitted and
refused untrusted user-message segments. Existing agentic judge prompt
snapshots use this helper, and later retrieved-document, skill, memory,
tool-output, and background-continuation admission points must use the same
helper or preserve its exact receipt shape, including the optional `source_id`
field for retrieved segments, when they record prompt-boundary evidence.

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
tool observation normalizer by reusing
`worker.runtime.untrusted_context.untrusted_context_receipt`. It does not
replace source-specific owner checks or prompt admission checks. Skill, memory,
RAG, chat prompt assembly, and background-job continuation surfaces must still
add their own admission or refusal receipts when they decide whether to
include, reject, or re-scope a tool observation in a final prompt.

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
