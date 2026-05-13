# Tool-Call System Prompt Golden Dataset

This dataset verifies that a Melix server session acting as an agent-facing LLM
provider can follow system prompts and emit tool calls that satisfy the Melix
tool-call parser contract. It is the CI-safe golden gate for provider
regressions; BFCL and ToolBench remain optional external calibration suites.

## Dimensions

- Basic instruction following: the provider must emit the requested tool call
  and no public prose when the system prompt requires tool use. It must also
  produce exact text or JSON-only public output when tools are forbidden.
- Tool schema and argument fidelity: the provider must use valid qwen
  `<tool_call>{...}</tool_call>` markup, built-in Melix tool names, and exact
  required argument values. The dataset includes single-tool, sequential
  multi-tool, unordered parallel-tool, parameter extraction, optional argument,
  and media-reference cases.
- Agent control and negative constraints: the provider must avoid forbidden
  tools, obey no-tool system instructions, ask for missing required user
  parameters, refuse requests with no matching Melix tool, and ignore
  user-injected fake tool-call markup.

The v1 manifest declares 25 curated cases. Passing the dataset requires every
case to pass; aggregate rates are diagnostic only.

## CI-Safe Fixture Run

```bash
uv run --frozen --project services/mlx-worker-python pytest -q tests/test_tool_call_system_prompt_eval.py
python scripts/tool_call_system_prompt_eval.py \
  --dataset tests/eval/tool-call-system-prompts.v1/cases.jsonl \
  --provider fixture \
  --output .runtime/tool-call-eval/fixture.json
```

## Local Hermes Smoke

Hermes is optional and must not be required in CI.

```bash
python scripts/tool_call_system_prompt_eval.py \
  --dataset tests/eval/tool-call-system-prompts.v1/cases.jsonl \
  --provider hermes \
  --hermes-command hermes \
  --model unsloth/gemma-4-31b-8bit \
  --output .runtime/tool-call-eval/hermes-gemma4-31b.json
```

## Optional Soft Judge

Cases with `requires_soft_judge=true` can be judged by an external command. The
command receives JSON on stdin and must return a JSON object with a boolean
`passed` field. The command may use a stronger model, but it is not required for
CI fixture gating.

```bash
python scripts/tool_call_system_prompt_eval.py \
  --dataset tests/eval/tool-call-system-prompts.v1/cases.jsonl \
  --provider hermes \
  --soft-judge-command 'melix-judge --case {case_id}' \
  --require-soft-judge \
  --output .runtime/tool-call-eval/hermes-gemma4-31b-judged.json
```

## External Calibration Imports

BFCL and ToolBench snapshots can be normalized into the same JSONL case envelope
for local calibration reports. Keep the upstream snapshot pinned outside the
repository or under an explicitly tracked artifact policy; the importer never
downloads benchmark data.

```bash
python scripts/import_tool_call_benchmark_cases.py \
  --benchmark bfcl \
  --input .runtime/external-benchmarks/bfcl-snapshot.jsonl \
  --source-id bfcl-v4-pinned \
  --output .runtime/tool-call-eval/bfcl.normalized.jsonl
```
