# Issue 352: Capability Receipts And Typed Unsupported Reasons

## Objective

Issue #352 defines the capability/receipt slice under the acceleration operator
surface. Melix needs a product-owned contract that reports model task support,
acceleration modes, draft compatibility, speculative-head metadata consistency,
and typed refusal reasons before runtime execution starts.

## Contract

The control-plane model catalog is the source of truth for operator-visible
capability receipts. Each `ModelSummary` exposes:

- task capability receipts for completion, embedding, vision, tools, reasoning,
  and insert-style affordances, including provenance and unsupported reasons
- an acceleration capability receipt with requested and resolved modes, target
  capability, optional drafter capability, supported modes, valid draft IDs,
  and recovery hints
- a speculative-head receipt that distinguishes configured metadata, indexed
  weights, drop flags, runtime availability, and metadata inconsistency

Non-baseline acceleration is fail-closed. A request may proceed only when the
resolved model receipt marks the requested acceleration mode as supported. A
speculative decode request must also satisfy the configured draft pairing. When
the receipt refuses a request, the request path returns a typed unsupported
reason and records the refusal in the worker execution metadata.

## Implementation Slices

### Slice 1 - Schema And Catalog Receipts

- Add receipt messages to the control-plane protobuf schema and regenerate
  Swift/Python protocol artifacts.
- Build receipts from existing model summary fields and `settings.ext`
  metadata.
- Keep baseline support explicit for all visible models.

### Slice 2 - Discovery And Public Metadata

- Surface receipt JSON through `/api/capabilities`.
- Surface the same summary through `melix capabilities --json`.
- Preserve existing capability and alias discovery fields for compatibility.

### Slice 3 - Early Request Refusal

- Resolve requested acceleration against the target receipt before dispatch.
- Refuse unsupported mode, missing draft, invalid draft, and inconsistent
  speculative-head metadata with typed reasons.
- Preserve baseline cleanup of draft fields when baseline is selected.

## Performance Probes And Metrics

- Measurement point: control-plane scheduling before worker dispatch.
- Success metric: unsupported acceleration requests are rejected before worker
  `generate`, `prefill`, or `decode` is called.
- Success metric: `/api/capabilities` contains stable receipt objects for every
  listed model.
- Success metric: request metadata records `requested_acceleration_mode`,
  `resolved_acceleration_mode`, `target_capability`, `drafter_capability`, and
  `unsupported_reason` for accepted accelerated requests; refused requests
  return the same typed reason before worker dispatch.
- Probe overhead: minimal. Receipt resolution is in-memory catalog metadata
  lookup and string/list parsing.

## Verification

- Protocol generation check for schema and generated artifacts.
- Model catalog tests for task, acceleration, draft, and speculative-head
  receipt fixtures.
- Runtime discovery tests for capability JSON payloads.
- Request coordinator tests proving invalid accelerated requests are rejected
  before worker dispatch.
- Changed-scope coverage report for the touched Swift control-plane and CLI
  tests.
