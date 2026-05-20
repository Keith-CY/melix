# Melix Agentic Trajectory Dataset Contract

## Purpose

This specification governs the repository-owned trajectory package shape for
the OpenSearch-VL alignment direction tracked by issue #664. Melix needs one
trace contract that can be consumed by:

- LoRA supervised fine-tuning
- reinforcement-learning rollout and reward construction
- benchmark request generation
- evaluation sample execution and scoring

The contract exists so training, rollout, benchmark, and evaluation do not
invent incompatible representations for multimodal tool-use trajectories.

## Methodology Source

This contract is informed by the OpenSearch-VL recipe:

- `https://github.com/shawn0728/OpenSearch-VL`
- `https://github.com/shawn0728/OpenSearch-VL/blob/main/SFT/README.md`
- `https://github.com/shawn0728/OpenSearch-VL/blob/main/RL/README.md`

Melix does not import that stack directly. The upstream recipe uses cold-start
agentic SFT, a shared visual and retrieval tool environment, and multi-turn
RL rollouts with fatal-aware reward handling. Melix maps those ideas onto its
local-first ownership model:

- Swift owns operator orchestration, request admission, and artifact routing.
- Python workers own dataset package normalization, deterministic local tool
  execution, reward summaries, and persisted sample evidence.
- Repository specs, plans, tests, and saved artifacts remain the source of truth
  for shipped behavior claims.

## Scope

This contract applies to:

- `agentic_tool_trace` training dataset packages
- normalized trajectory snapshots written before LoRA or rollout execution
- trajectory validation metrics
- trace-level fatal, reward, and leakage markers
- provenance fields written into LoRA, RL, benchmark, and evaluation artifacts
- child issues that implement issue #664 milestones

This contract does not require:

- network-backed search in CI
- full-parameter multimodal training
- importing CUDA training infrastructure
- claiming benchmark or evaluation improvement without persisted run artifacts
- closing issue #664 before all milestone issues land and are verified

## Existing Melix Anchors

Current implementation anchors that future slices must reuse:

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
  - accepts `agentic_tool_trace` packages
  - validates required trace identity, question, turns, and final answer fields
  - validates that tool observations reference prior assistant tool calls
  - reports trace quality metrics and explicit leakage findings
- `services/mlx-worker-python/fixtures/training/agentic-tool-trace.dev.v1/`
  - fixture package for the first repository-owned trace shape
- `services/mlx-worker-python/worker/runtime/tool_registry.py`
  - defines the built-in tool registry receipt
- `services/mlx-worker-python/worker/runtime/tool_observation.py`
  - defines sanitized `melix.agentic_tool_observation.v1` records
- `services/mlx-worker-python/worker/runtime/agentic_tools.py`
  - executes deterministic fixture-backed agentic tool calls
- `docs/unified-agentic-tool-runtime-contract.md`
  - governs shared tool registry, observation, execution, replay, and evidence
    semantics

## Package Layout

A trajectory package is a `melix.training_dataset_package.v1` directory with:

- `manifest.json`
- `samples.jsonl`
- optional `valid.jsonl`
- optional media or fixture assets referenced by URI fields

`manifest.json` must include the standard training package fields:

- `schema_version`: `melix.training_dataset_package.v1`
- `dataset_id`
- `format`: `agentic_tool_trace`
- `sample_count`
- `version`

The v1 trajectory row schema name is `melix.agentic_tool_trace.v1`. Existing
packages identify it through `format: agentic_tool_trace`; new packages and
downstream artifacts should also persist `trajectory_schema_version:
melix.agentic_tool_trace.v1` when provenance fields are introduced.

Trajectory packages may also include:

- `trajectory_schema_version`
- `toolset_version`
- `registry_schema_version`
- `reward_policy_id`
- `source_dataset_id`
- `source_split`
- `source_revision`
- `media_root`
- `license`
- `leakage_policy_id`

The package loader must preserve unknown manifest fields when writing downstream
snapshots unless a child issue explicitly narrows that behavior.

## Sample Envelope

Each `samples.jsonl` row is one trajectory sample. Required fields are:

- `trace_id`: stable sample identity inside the package
- `question`: user-facing task prompt or question
- `turns`: non-empty ordered conversation and tool-observation sequence
- `final_answer`: answer emitted by the assistant after tool use

Optional but preserved fields are:

- `media_refs`
- `tools`
- `expected_answer`
- `evidence_ids`
- `reward`
- `fatal_stage`
- `failure_stage`
- `leakage_terms`
- `tool_calls`
- `tool_fixture_context`
- `agentic_tool_registry`
- `agentic_tool_calls`
- `agentic_tool_observations`

### Turn Shape

Every turn must include `role` with one of:

- `system`
- `user`
- `assistant`
- `tool`

`system` and `user` turns must include non-empty `content`.

`assistant` turns must include either non-empty `content` or a `tool_call`
object.

`tool_call` objects must include:

- `id`
- `name`
- optional `arguments`

`tool` turns must include:

- `tool_call_id`
- non-empty `observation`

`tool_call_id` must reference a prior assistant `tool_call.id` in the same
sample.

### Media References

`media_refs` identifies images, documents, pages, audio, or other local
evidence inputs used by the trajectory. Each media reference should include:

- `id`
- `uri`
- optional `mime_type`
- optional `sha256`
- optional `source`
- optional `metadata`

Media references may point to local package files, managed Melix artifacts, or
fixture URIs. Network URLs are allowed only when the consuming slice records the
external dependency and persists replay evidence.

### Rewards And Fatal Markers

The `reward` object must be treated as structured data, not a free-text note.
Child issues that consume rewards must define the keys they read. The common v1
keys are:

- `final_answer`
- `tool_efficiency`
- `format`
- `query_quality`
- `grounding`
- `total`

`fatal_stage` records the first stage that invalidates later trajectory tokens
or observations. Supported stage names are:

- empty string for no fatal stage
- `parser_failure`
- `tool_execution_failure`
- `tool_timeout`
- `observation_invalid`
- `answer_invalid`
- `post_fatal_continuation`

RL and evaluation slices must not treat post-fatal continuation as normal
successful reasoning.

### Leakage Markers

`leakage_terms` lists explicit forbidden answer or shortcut terms that should
not appear in the question, intermediate turns, tool-call arguments, or
observations. When a leakage term is found, the package remains inspectable but
the sample must be reported as dirty with the reason `leakage_terms`.

This rule supports data construction and evaluation hygiene. It does not replace
semantic leakage review by downstream benchmark or evaluation suites.

## Validation Metrics

Trajectory validation must report machine-readable metrics at package,
snapshot, or artifact boundaries. The required v1 metrics are:

| Metric | Meaning |
| --- | --- |
| `agentic_trace_count` | Number of trajectory samples inspected. |
| `tool_call_count` | Total assistant tool calls. |
| `tool_observation_count` | Total tool observations. |
| `fatal_trace_count` | Traces with non-empty `fatal_stage`. |
| `leakage_count` | Traces with explicit leakage findings. |
| `trace_turn_count_min` | Minimum turn count across inspected traces. |
| `trace_turn_count_max` | Maximum turn count across inspected traces. |
| `trace_turn_count_avg` | Average turn count across inspected traces. |
| `media_ref_count` | Total media references. |
| `reward_coverage_count` | Traces with structured reward objects. |
| `fatal_stage_coverage_count` | Traces with the `fatal_stage` field present. |

Performance probes and success metrics for child issues must name these fields
or justify why they are not relevant to that slice.

## Normalized Snapshots

Before LoRA training or rollout consumes a trajectory package, Melix must write
a normalized snapshot under the job directory. The snapshot manifest must keep:

- source dataset id and package path
- `format: agentic_tool_trace`
- package version
- train and validation sample counts
- selected split
- quality metrics
- toolset and registry versions when available
- reward policy id when available
- leakage policy id when available

The snapshot JSONL rows must preserve the sample envelope and normalized turns.
Consumers must read the snapshot, not the mutable source package, once a job has
started.

For LoRA SFT, the snapshot also writes a trainer-facing projection. The source
snapshot manifest keeps `format: agentic_tool_trace` and records
`trainer_format: chat_messages`. `samples.jsonl`, `train.jsonl`, and
`valid.jsonl` contain the supervised `messages` rows consumed by the local
trainer. A single source trace may produce multiple trainer rows: one for each
assistant tool-call span that should receive loss and one for the final-answer
span. Sibling `agentic-traces.train.jsonl` and
`agentic-traces.valid.jsonl` files preserve the original normalized trace rows
for provenance, audit, replay, and later RL/evaluation reuse.

The v1 SFT projection formats:

- top-level media references as an optional system message
- assistant `tool_call` objects as deterministic JSON text in an assistant
  message
- tool observations as `tool` role messages bound to the source tool-call id
- the final answer as the supervised assistant answer

Response-only and mask-prompt support for `agentic_tool_trace` depends on this
row split. MLX-LM's current chat dataset exposes one contiguous prompt boundary
per row, so Melix ends each projected row with the assistant span that should
receive loss. Earlier user, system, assistant reasoning, and tool-observation
messages remain context and are masked by `mask_prompt=true`. Each projected row
records a `response_only_boundary` object with:

- `policy_id: melix.agentic_tool_trace.response_only_boundaries.v1`
- `mask_prompt: true`
- `trainable_role: assistant`
- `trainable_kind: tool_call` or `final_answer`
- `trainable_message_index`
- `trace_id` when available

The normalized snapshot manifest records `source_trace_sample_count`,
`trainer_sample_count`, `agentic_sft_boundary_policy`, and projection metrics
for trainer rows plus response-only/mask-prompt boundary counts. Adapter
receipts keep `dataset_sample_count` as the source trace count and add
`trainer_dataset_sample_count` for the expanded trainer rows.

The normalized snapshot manifest also records `agentic_sft_token_metrics` for
agentic SFT projections. The metric object uses the repository-owned
`whitespace_v1` estimator and includes `source_trace_count`, `trace_tokens`,
`tool_call_tokens`, `observation_tokens`, and `final_answer_tokens` across the
train and validation traces. LoRA adapter receipts that consume the snapshot
must copy this metric object and expose stable `training.agentic_sft.*` aliases
for these token counts so downstream reports can tie adapter quality and
training cost back to the source trace, tool-call, observation, and final-answer
budget.

LoRA SFT over `agentic_tool_trace` packages is a distinct supervised objective.
The operator still selects an SFT `training_mode` such as `lora`, `qlora`, or
`dora`, but the normalized worker config and adapter receipt must record
`training_objective: agentic_sft` and
`dataset_contract: agentic_tool_trace`. The trainer-facing rows remain
`chat_messages`; the source dataset format and dataset contract remain
`agentic_tool_trace` so provenance, validation, and later RL/evaluation reuse
do not collapse into generic SFT. Explicit incompatible
`training_objective` overrides must fail before backend execution.

## Provenance Fields

LoRA, RL, benchmark, and evaluation artifacts that consume a trajectory package
must expose trajectory provenance. The stable field names are:

- `trajectory_dataset_id`
- `trajectory_dataset_version`
- `trajectory_schema_version`
- `trajectory_package_path`
- `trajectory_split`
- `trajectory_snapshot_manifest_path`
- `trajectory_trace_digest`
- `trajectory_toolset_version`
- `trajectory_registry_schema_version`
- `trajectory_reward_policy_id`
- `trajectory_leakage_policy_id`
- `trajectory_quality_metrics`

Artifact-specific schemas may nest these fields under a `trajectory` object when
that is the established local pattern, but export paths must keep the names
machine-readable and documented in the relevant plan or spec.

## Benchmark And Evaluation Evidence

Benchmark and evaluation claims involving trajectories are valid only when
backed by persisted artifacts. Acceptable evidence includes:

- normalized trajectory snapshot manifest
- benchmark request or result JSONL with trajectory provenance fields
- evaluation sample JSONL with tool calls, observations, final answer, parse
  status, score, and failure stage
- run evidence JSON that links the package, split, snapshot, and result export
- report bundle summaries generated from those artifacts

Prose summaries, terminal output, or PR comments do not replace persisted
artifacts.

## Executable Child Issue Matrix

The following child issues are the execution path for issue #664. Each child
issue must keep its own PR narrow, update this spec or a narrower plan before
broad implementation, and report changed-scope verification according to
`AGENTS.md`.

| Parent Milestone | Child Issue | File Scope | Required Tests | Required Metrics | Known Gaps |
| --- | --- | --- | --- | --- | --- |
| M1: define the trajectory schema and package layout | #665 milestone tracker | this spec, `docs/plans/2026-05-14-opensearch-vl-agentic-trajectory-contracts.md`, and child issues #666 and #667 | documentation validation, child issue audit, `git diff --check` | `N/A` for tracker-only docs; child issues must define measurable metrics | no runtime behavior changes in tracker PRs |
| M1: define the trajectory schema and package layout | #666 write schema fields | `services/mlx-worker-python/worker/model_ops/training_dataset.py`, fixtures under `services/mlx-worker-python/fixtures/training/agentic-tool-trace*.v1/`, this spec if fields change | focused training dataset builder tests for required fields, role validation, tool-call references, media refs, rewards, fatal markers; changed-scope coverage | trace count, turn count min/max/avg, tool-call count, observation count, media ref count, reward coverage, fatal-stage coverage | no LoRA optimizer changes; no benchmark/evaluation export changes |
| M1: define the trajectory schema and package layout | #667 fixtures and negative schema tests | fixture packages, `services/mlx-worker-python/tests/test_training_dataset_builder.py`, optional schema helper under `scripts/` if validation is factored out | valid fixture load tests; malformed turns; unmatched tool observations; answer leakage; dirty sample reasons; changed-scope coverage | leakage count, dirty sample count, fixture sample count, validation duration | semantic leakage review remains manual unless a later evaluator adds it |
| M2: materialize and validate trajectory packages | #668 milestone tracker | this spec and child issues #669 and #670 | documentation validation, child issue audit, `git diff --check` | `N/A` for tracker-only docs; child issues must define measurable metrics | no runtime behavior changes in tracker PRs |
| M2: materialize and validate trajectory packages | #669 normalized trajectory snapshots | `services/mlx-worker-python/worker/model_ops/training_dataset.py`, LoRA dataset snapshot writers, relevant Swift bridge only if CLI/API payloads change | snapshot manifest tests; local package and HF/materialized package resolution tests when supported; LoRA prep tests proving jobs read the normalized snapshot | snapshot write duration, sample counts, validation counts, trace digest, cache hit/miss if materialization is cached | no adapter manifest provenance until #672 |
| M2: materialize and validate trajectory packages | #670 validation metrics | `training_dataset.py`, report/export helpers that surface dataset quality, tests under `services/mlx-worker-python/tests/` | quality metric aggregation tests; fatal-stage coverage tests; reward coverage tests; malformed package rejection; changed-scope coverage | required validation metrics listed in this spec | no benchmark/evaluation score claims without #673 artifacts |
| M3: expose trajectory provenance in artifacts | #671 milestone tracker | this spec and child issues #672 and #673 | documentation validation, child issue audit, `git diff --check` | `N/A` for tracker-only docs; child issues must define measurable metrics | no runtime behavior changes in tracker PRs |
| M3: expose trajectory provenance in artifacts | #672 adapter and RL provenance | LoRA adapter manifest writers, normalized dataset snapshot readers, RL alignment artifact writers, related tests | adapter manifest tests; RL trace digest tests; reward-policy id persistence tests; changed-scope coverage | trajectory trace digest, reward policy id presence, provenance field coverage, artifact byte size | does not prove benchmark/evaluation performance |
| M3: expose trajectory provenance in artifacts | #673 benchmark and evaluation provenance | benchmark/evaluation stores, export builders, run evidence/report bundle code, Swift export bridge only if public fields change | benchmark export tests; evaluation sample JSONL tests; run evidence tests; report bundle tests; persisted artifact smoke when behavior changes | sample count, tool-call count, observation count, failure-stage count, score coverage, export duration | real model quality claims require saved benchmark/evaluation runs |

## Verification Gates

Every behavior-changing PR under issue #664 must report:

- governing spec or plan path
- changed file scope
- focused test commands and outcomes
- changed-scope coverage at or above 95 percent, or a precise reason why the
  scope is not measurable
- metrics report for the changed scope
- persisted benchmark or evaluation artifacts whenever measured behavior is
  claimed
- known gaps and deferred work

Documentation-only PRs under this contract may report:

```text
Coverage and Metrics: N/A: documentation-only trajectory contract update; no executable runtime path changed.
```

## Current Status

As of this specification, Melix already has the first `agentic_tool_trace`
dataset ingestion anchor and deterministic agentic tool runtime anchors. Issue
#664 should remain open until #665, #668, and #671, plus their executable child
issues, have landed with current local verification evidence and the shipped
behavior can be audited from repository artifacts.
