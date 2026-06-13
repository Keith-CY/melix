# Issue 1761 Tool-Turn Receipt Evidence

## Goal

Preserve untrusted-context receipt evidence when agentic tool observations are
projected into benchmark request rows. The execution runtime already emits
`untrusted_context_receipts`; this slice makes the downstream tool-turn evidence
row expose receipt counts and schema metadata without requiring consumers to
parse the full observation JSON.

## Scope

This slice is limited to Python worker productization schemas used for benchmark
request rows:

- keep existing `tool_observation_json` unchanged for compatibility;
- add scalar receipt metadata fields for tool-turn rows derived from existing
  observation evidence;
- avoid copying raw tool payload, prompt text, retrieved text, media URIs, or
  private source payloads into the new fields;
- update schema tests and this contract plan.

Out of scope:

- changing agentic tool execution, receipt creation, or prompt assembly;
- adding live RAG, skill, memory, MCP, workflow, or local-job execution wiring;
- changing CSV export ordering beyond appending evidence columns;
- parsing or storing receipt bodies in scalar CSV fields.

## Architecture

`benchmark_store.py` converts benchmark context rows into request rows. Tool
turn rows pass the full observation to `build_serving_benchmark_request_row`,
which serializes it as `tool_observation_json`. That preserves evidence but
forces downstream report code to parse arbitrary JSON before it can tell whether
untrusted-context receipt evidence was present.

This slice adds derived scalar fields to request rows:

- `untrusted_context_receipt_schema`
- `untrusted_context_receipt_count`

The values come from the observation's existing `untrusted_context_receipts`
list. The schema field is set only when at least one receipt is a mapping with a
string `schema_version`; otherwise it remains empty. The count field records the
number of mapping receipts only. This keeps malformed non-dict receipt values
from inflating evidence counts and avoids copying receipt bodies into the CSV
surface.

## Performance Probes And Metrics

The changed path is a small linear scan over each observation's receipt list
while building benchmark request rows. It does not add filesystem, network,
model, ranking, or scheduler work.

Verification must include:

- focused pytest for benchmark schema/store behavior;
- changed-line coverage for touched Python files at 95 percent or higher;
- `git diff --check`;
- scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the repository pre-commit gate before opening the PR.

## Success Criteria

- Tool-turn request rows expose receipt schema and count derived from existing
  agentic tool observations.
- Existing observation JSON remains unchanged and still contains the full
  receipt evidence.
- New scalar fields do not include raw prompt text, tool payload, retrieved
  content, media URIs, or receipt bodies.
- Rows with no valid mapping receipts report count `0` and empty schema.
