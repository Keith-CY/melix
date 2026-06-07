# Issue 1761 Untrusted Tool Boundary Plan

## Goal

Add a first fail-closed untrusted-context boundary for deterministic agentic tool execution so malformed retrieved fixture content, tool arguments, and status-control payloads become typed observations instead of being coerced into trusted strings.

## Scope

This slice covers the Python worker's deterministic agentic tool runtime:

- `worker.runtime.agentic_tools`
- fixture-backed `text_search`, `image_search`, `visit`, `layout_parse`, `image_crop`, and `local_compute`
- agentic tool status overrides used by tests and replay fixtures
- shared runtime tests and the governing agentic tool contract

This slice does not implement owner-scoped retrieval, prompt assembly wrappers for every future RAG surface, workspace path resolution, or scheduled/background job chaining. Those remain follow-up work under #1761.

## Architecture

The best end-state is a shared untrusted-value validation layer used before any retrieved data, tool output, local file metadata, skill payload, or background-job artifact can cross into prompt construction or tool execution. This PR delivers the first vertical slice by adding typed runtime validation at the existing deterministic agentic tool entrypoint, where retrieved fixture content and model-produced tool arguments already meet observation receipts.

Validation must fail closed and preserve evidence:

- reject unexpected container and scalar types before URL lookup, corpus filtering, page extraction, crop/layout handling, or status override handling
- emit a failed tool observation with `reason = invalid_untrusted_input_type`
- include `source_type`, `source_id`, `field`, `expected_type`, `actual_type`, and `corrective_action`
- keep existing successful tool behavior unchanged

## Performance Probes And Metrics

Changed runtime code is expected to be covered by the existing agentic tool tests and PR-scoped performance selection. If the changed file does not select a direct synthetic probe, the PR will include:

- focused pytest for the agentic tool runtime typed rejection paths
- changed-scope coverage for modified files, target at least 95 percent
- local pre-commit scoped performance report with `Status: ok`, regressions `0`, and verification failures `0`

The expected overhead is limited to a few `isinstance` checks per deterministic tool call and per fixture row. No production network or model execution path is added.

## Implementation Steps

1. Add failing tests in `services/mlx-worker-python/tests/test_agentic_tools.py` for:
   - non-string `visit.url` tool argument
   - non-string retrieved page `text`
   - non-string text corpus document `text`
   - non-string status override `message`
2. Implement typed `AgenticToolRuntimeError` details and small validation helpers in `worker.runtime.agentic_tools`.
3. Apply the helpers to tool arguments, fixture context containers, retrieved page/corpus/crop/layout fields, and status overrides.
4. Update `docs/unified-agentic-tool-runtime-contract.md` with the untrusted fixture boundary and receipt shape.
5. Run focused tests, changed-scope coverage, `git diff --check`, commit, let pre-commit run the full local gate, then open and monitor the PR.

## Success Criteria

- Malformed untrusted values produce failed observations rather than silent coercion or empty search/page results.
- Successful deterministic tool calls keep their existing observation shape.
- Typed rejection receipts include enough source metadata for operator/debug evidence without exposing hidden identifiers beyond the fixture source id already in use.
- Focused tests and changed-scope coverage pass.
- PR-scoped performance report has no regressions or verification failures.
