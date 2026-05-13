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

Fatal-aware behavior must distinguish:

- valid pre-failure reasoning
- failed tool execution
- timeout
- parser failure
- post-fatal continuation that must not be treated as normal reasoning

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

As of this contract, Melix has the initial registry, observation, and
`agentic_tool_trace` data-foundation anchors. The unified tool runtime is not
complete until the child issues above land with current local verification
evidence. Issue #674 should therefore remain open while #675, #678, and #681
remain open.
