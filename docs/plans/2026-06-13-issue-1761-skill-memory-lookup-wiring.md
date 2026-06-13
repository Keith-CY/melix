# Issue 1761 Skill And Memory Lookup Wiring

## Goal

Wire concrete deterministic skill and memory lookup tool paths through
`worker.runtime.skill_memory_context.project_skill_memory_lookup_result` so the
existing side-effect-free projection becomes part of an executable caller path.

## Scope

This slice is limited to the Python worker deterministic agentic tool runtime:

- add fixture-backed `skill_lookup` and `memory_lookup` opt-in selectable
  catalog adapters;
- keep lookup payloads small and deterministic: `query`, `store_ref`,
  `results`, and `result_count`;
- convert selected skill and memory rows into already-redacted lookup records;
- derive source untrusted-context receipts from
  `project_skill_memory_lookup_result`;
- update registry tests and the unified runtime contract.

Out of scope:

- reading skill files from disk;
- creating a durable skill store or memory store;
- ranking, embedding, or semantic lookup;
- mutating memories, sessions, or chat state;
- copying raw skill or memory payloads into receipt JSON;
- changing existing retrieval, visit, MCP, or tool-observation behavior.

## Architecture

`agentic_tools.py` already provides deterministic fixture-backed lookup adapters
for retrieval search. This slice adds symmetric fixture-backed adapters for
skill and memory lookup so tests and evaluations can exercise concrete
skill/memory prompt-boundary receipts without introducing live stores.

The default no-selection `built_in_tool_config()` remains limited to the
existing six tool schemas. `skill_lookup` and `memory_lookup` live in the
selectable agentic tool catalog, where explicit names, vector routing, keyword
routing, or deterministic replay can opt in without increasing the default
schema cost.

The adapters select rows from `fixture_context["skill_store"]` and
`fixture_context["memory_store"]`, enforce the existing owner-scope check when
configured, build store records, and pass those records to
`project_skill_memory_lookup_result`. The returned admitted and refusal receipts
are attached to the existing observation payload through
`_untrusted_context_receipts`. The projection's `lookup_message` is not emitted
because the tool observation already owns the visible lookup result payload.

## Performance Probes And Metrics

The changed path adds two opt-in catalog schemas and performs linear scans over
fixture-provided selected stores. There is no filesystem access, network work,
embedding inference, ranking model, scheduler work, or memory persistence. The
default no-selection tool schema must stay at the previous six-tool cost.

Verification must include:

- focused red/green pytest runs for `test_agentic_tools.py` and
  `test_tool_registry.py`;
- changed-line coverage for touched Python files at 95 percent or higher;
- `git diff --check`;
- a scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the required pre-commit local gate before pushing the PR.

If the performance report flags default registry schema growth as an in-scope
regression, shrink the tool contracts, make the adapters opt-in through
selection, or revert the registry expansion before merging. Do not accept a
schema-size regression without explicit rationale and a passing rerun.

## Implementation Steps

1. Add failing tests proving `skill_lookup` and `memory_lookup` are exported by
   the selectable catalog with stable descriptors and selection behavior while
   remaining outside the default no-selection tool set.
2. Add failing tests proving both adapters pass selected results through
   `project_skill_memory_lookup_result` with stable store-record fields.
3. Add failing tests proving accepted skill and memory receipts are redacted and
   projection refusal receipts remain attached to observations.
4. Implement the minimal catalog descriptors, keyword hints, and adapter
   dispatch.
5. Implement store row normalization, owner-scope checks, record builders, and
   projection receipt attachment.
6. Update `docs/unified-agentic-tool-runtime-contract.md`.
7. Run focused tests, coverage, diff checks, scoped performance, and the
   required local gate before opening the PR.

## Success Criteria

- `skill_lookup` and `memory_lookup` observations expose deterministic lookup
  payloads and include source-specific untrusted-context receipts.
- The default no-selection tool schema remains limited to the existing six
  built-in tools; skill/memory lookup is selected only by explicit names,
  routing, or replay.
- Selected rows are projected through
  `project_skill_memory_lookup_result` before source receipts reach
  `normalize_tool_observation`.
- Receipt JSON omits raw skill summaries, memory text, query strings, store
  refs, and private prompt text.
- Existing built-in tools and retrieval lookup wiring remain unchanged.
