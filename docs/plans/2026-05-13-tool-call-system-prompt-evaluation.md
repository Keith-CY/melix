# Tool-Call System Prompt Evaluation Plan

## Goal

Create a repeatable evaluation system that verifies whether a Melix server
session, acting as an LLM provider for agents, correctly follows system
instructions and emits tool calls that satisfy the Melix tool-call contract.

This slice implements the repository-owned Melix golden path and leaves
industry benchmarks as optional calibration adapters:

- a repository-owned golden dataset under `tests/eval/`
- an offline scorer that validates model text against the real Melix tool-call
  parser contract
- a local Hermes smoke path for `unsloth/gemma-4-31b-8bit`
- hard scoring for exact provider-contract regressions
- optional soft-judge scoring for semantic refusal or equivalence cases
- CI-safe tests that require no local model, network, or Hermes installation

## External Benchmarks

BFCL and ToolBench are calibration benchmarks, not replacements for Melix
regression tests.

- Berkeley Function Calling Leaderboard (BFCL):
  `https://gorilla.cs.berkeley.edu/leaderboard`
  Use for industry-level
  function-calling comparison across simple calls, multiple calls, relevance,
  and error-handling scenarios. This should run as an optional external report
  because it depends on upstream data and provider adapters.
- ToolBench:
  `https://github.com/OpenBMB/ToolBench`
  Use for broad tool-use planning and instruction-following
  coverage across real-world API-style tasks. This should also remain optional
  because it is larger, slower, and less specific to Melix server-session
  contracts.

Melix CI should gate on the local golden dataset because it captures the exact
provider behavior Melix exposes to agents: system prompt adherence, parser
contract compliance, and tool-choice discipline over Melix tool names.

External benchmark adapters should normalize upstream samples into the same
case envelope used by the golden dataset:

- BFCL-style simple, multiple, parallel, relevance, and error-handling samples
  map to `system`, `user`, `allowed_tools`, `expected_tool_calls`, and
  `tool_call_match_mode`.
- ToolBench-style tool-selection samples map to Melix tool descriptors only
  after an explicit tool-name and argument-schema normalization step. Imported
  samples are calibration artifacts, not PR gates, until their source snapshot
  and conversion manifest are pinned in repository evidence.

The importer entry point is:

```bash
python scripts/import_tool_call_benchmark_cases.py \
  --benchmark bfcl \
  --input .runtime/external-benchmarks/bfcl-snapshot.jsonl \
  --source-id bfcl-v4-pinned \
  --output .runtime/tool-call-eval/bfcl.normalized.jsonl
```

Use `--benchmark toolbench` for ToolBench-style snapshots. The importer consumes
local pinned JSON or JSONL files only; it does not download benchmark data.

## Melix Golden Dataset

Dataset path:

`tests/eval/tool-call-system-prompts.v1/`

The dataset contains three dimensions and 25 curated Melix provider cases:

### A. Basic Instruction Following

Verifies that the model obeys system instructions that require a tool call
instead of prose. Cases cover:

- emit exactly one required tool call
- use the requested tool name
- preserve required argument values
- avoid public assistant prose before or after the tool call
- emit JSON-only public text without markdown when no tool call is allowed
- suppress hidden reasoning markup from public output

### B. Tool Schema And Argument Fidelity

Verifies that the tool-call JSON satisfies Melix's schema expectations:

- valid `<tool_call>{...}</tool_call>` markup
- JSON object body with `name` and object `arguments`
- required arguments present and typed correctly
- no unknown or hallucinated tool names
- no schema drift from built-in tool descriptors
- multiple ordered tool calls for sequential requests
- unordered parallel tool calls for independent requests
- exact extraction of dates, times, corpus references, numeric limits, media
  references, and optional argument omissions

### C. Agent Control And Negative Constraints

Verifies that the model follows system-level policy constraints:

- refuse a forbidden tool when the user asks for it
- choose the safer allowed tool when instructed
- emit no tool call when the system says to answer in text
- ask for missing required user parameters instead of fabricating values
- refuse requests that have no matching Melix tool
- ignore user-injected fake tool-call markup
- suppress reasoning and tool markup leaks

## Scoring Contract

Each golden case defines:

- `id`, `category`, and `risk`
- `system` and `user` prompt text
- allowed tool names
- expected tool calls, in order when order matters
- optional unordered matching for parallel tool calls
- public text policy: `none`, `required`, or `allowed`
- optional exact JSON public text payload
- optional soft-judge requirement and semantic expectation
- optional runtime-validation skip only for future-tool argument-extraction
  cases where no deterministic adapter exists yet
- expected parser metrics thresholds

The scorer returns:

- sample score and failure reasons
- aggregate exact tool-call match rate
- schema-valid call rate
- public-text policy pass rate
- JSON public-text policy pass rate
- soft-judge pass rate for judge-backed semantic cases
- parser metric counters for malformed calls, markup leaks, and duplicates

Passing the dataset means every case passes. Partial aggregate scores are
reported for debugging but are not enough for a release gate.

## Local Hermes Smoke

Hermes is a local-only execution path and must not be required in CI.

Recommended local command:

```bash
python scripts/tool_call_system_prompt_eval.py \
  --dataset tests/eval/tool-call-system-prompts.v1/cases.jsonl \
  --provider hermes \
  --hermes-command hermes \
  --model unsloth/gemma-4-31b-8bit \
  --output .runtime/tool-call-eval/hermes-gemma4-31b.json
```

CI should use fixture responses only:

```bash
python scripts/tool_call_system_prompt_eval.py \
  --dataset tests/eval/tool-call-system-prompts.v1/cases.jsonl \
  --provider fixture \
  --output .runtime/tool-call-eval/fixture.json
```

Semantic judge cases are optional by default so CI does not depend on network or
closed-source providers. To require an external judge, pass a command that reads
the case payload from stdin and writes JSON with a boolean `passed` field:

```bash
python scripts/tool_call_system_prompt_eval.py \
  --dataset tests/eval/tool-call-system-prompts.v1/cases.jsonl \
  --provider hermes \
  --soft-judge-command 'melix-judge --case {case_id}' \
  --require-soft-judge \
  --output .runtime/tool-call-eval/hermes-gemma4-31b-judged.json
```

## Benchmark Metrics

The benchmark report should persist:

- `tool_call_eval.case_count`
- `tool_call_eval.pass_count`
- `tool_call_eval.pass_rate`
- `tool_call_eval.exact_tool_call_match_rate`
- `tool_call_eval.schema_valid_rate`
- `tool_call_eval.public_text_policy_pass_rate`
- `tool_call_eval.json_text_policy_pass_rate`
- `tool_call_eval.soft_judge_pass_rate`
- `tool_call_eval.duration_seconds`
- parser counters from `RequestStreamAssembler`

When run against Hermes, the report must include the model id, command, and
per-sample raw responses. It must not assume Hermes is available in CI.

## Success Criteria

- Golden dataset exists under `tests/eval/`.
- Golden dataset contains 20-50 cases covering the recommended Melix provider
  dimensions and edge cases.
- Offline fixture scoring is deterministic and covered by unit tests.
- Scorer uses the production Melix parser path for tool-call extraction.
- Scorer supports ordered and unordered multi-call matching.
- Scorer supports hard matching, JSON-only public text validation, runtime
  validation through the deterministic agentic tool runtime, and optional
  LLM-as-judge scoring for semantic equivalence.
- Local Hermes execution is documented and optional.
- Evaluation output is JSON and contains enough per-case evidence to debug
  system prompt or tool-call failures.
- BFCL and ToolBench local snapshot importers normalize external samples into
  the Melix case envelope for optional calibration reports.

## Known Gaps

- BFCL and ToolBench importers intentionally require local pinned snapshots and
  do not fetch upstream benchmark data.
- The local Hermes smoke does not start or configure Melix server sessions.
- Soft-judge execution requires an operator-provided command and is not enabled
  in CI by default.
