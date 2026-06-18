# Issue 1761 Layout And Crop Source Receipts

## Goal

Attach source-specific untrusted-context receipts to deterministic
`layout_parse` and `image_crop` tool observations so visual fixture evidence has
the same prompt-boundary audit trail as retrieved image search results.

## Scope

This slice is limited to the Python worker deterministic agentic tool runtime:

- keep `layout_parse` and `image_crop` payload shapes unchanged;
- keep existing owner-scope and invalid-type fail-closed behavior;
- attach one `retrieved_image` source receipt to each successful visual tool
  observation;
- keep short fixture identifiers visible in receipt `source_id`, but hash raw
  media references, paths, URIs, or long identifiers before receipt emission;
- reuse `worker.runtime.retrieval_context.admit_retrieved_image_context`;
- update the unified runtime contract for the concrete visual-tool wiring.

Out of scope:

- live image stores, OCR, layout extraction, crop generation, media fetches, or
  owner inference;
- changing the generic `tool_observation` receipt;
- copying raw layout text, crop text, media refs, paths, URIs, media bytes,
  prompt bodies, or private source payloads into receipt JSON.

## Architecture

The deterministic visual adapters already normalize untrusted fixture payloads
and fail closed before emitting observations. After the payload is shaped, each
adapter will pass a copy of the already-shaped observation payload through
`admit_retrieved_image_context` and attach the admitted receipt through
`_untrusted_context_receipts`. Receipt `source_id` values use short symbolic
fixture identifiers when they are already safe, and otherwise use
`image-ref:<sha256-prefix>` so source metadata does not expose raw media
references. `normalize_tool_observation` will continue to own the generic
tool-observation receipt and will append the visual source receipt outside the
payload.

## Performance Probes And Metrics

The change adds one in-memory admission call per successful `layout_parse` or
`image_crop` observation. It adds no filesystem access, network work, model
inference, ranking, scheduler behavior, or persistent state.

Verification must include:

- focused red/green pytest runs for the new visual receipt tests;
- focused `test_agentic_tools.py` coverage;
- changed-line coverage for touched Python files at 95 percent or higher;
- `git diff --check`;
- scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`;
- the required local gate before opening the PR.

## Implementation Steps

1. Add failing tests proving `layout_parse` and `image_crop` successful
   observations include source receipts with stable segment IDs, source IDs,
   owner-scope evidence, and no raw fixture text in receipt JSON.
2. Add a failing test proving both visual adapters call
   `admit_retrieved_image_context`.
3. Add a failing test proving visual source receipts hash raw media refs before
   emitting `source_id`.
4. Implement a small helper for visual source receipt admission and call it from
   `_layout_parse_payload` and `_image_crop_payload`.
5. Update `docs/unified-agentic-tool-runtime-contract.md`.
6. Run focused tests, coverage, diff checks, the scoped performance report, and
   the required local gate before opening the PR.

## Success Criteria

- `layout_parse` and `image_crop` payloads stay backward-compatible.
- Each successful visual tool observation includes exactly one source receipt
  with `source_type = retrieved_image` in addition to the generic
  `tool_observation` receipt.
- Owner-scoped visual fixture payloads set `owner_scope_checked = true` only
  after the existing owner check succeeds.
- Receipt JSON remains redacted from raw layout text, crop text, media refs,
  paths, URIs, media bytes, prompt bodies, and private source payloads.
