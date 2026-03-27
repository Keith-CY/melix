# Decision Record: Selective Swift Text Runtime

Date: 2026-03-27

## Context

Melix Phase 0 established a Swift-first control plane and a Python worker path for the first executable local runtime slice.

After Phase 0, the next architectural question is whether Melix should:

- keep the current mixed architecture with Python-heavy execution
- move latency-critical text execution into Swift while preserving the worker boundary
- or push toward a Swift-only worker model

The main pressure behind this question is the text hot path. Swift has strong affinity with Apple platform runtime concerns and can reduce overhead in latency-sensitive local generation flows. At the same time, Melix still needs a broad execution plane for multimodal work, tooling, conversion, diagnostics, and benchmarking.

## Decision

Melix will adopt a selective runtime split:

- the Swift control plane remains the orchestration source of truth
- Melix will add an independent Swift text worker as the default text execution engine
- Python workers remain the primary execution plane for multimodal, embeddings, rerank, image, audio, convert, doctor, and bench flows
- the control-plane-to-worker boundary stays intact and continues to use the shared worker RPC protocol over local sockets
- the first Swift runtime phase covers the text `Generate` hot path, lifecycle, and abort only
- Swift text worker failures should fail explicitly rather than silently falling back to the Python text path

## Rationale

- This keeps the product-facing control plane and menu bar surfaces in Swift, where native lifecycle, XPC, and long-lived product logic fit naturally.
- It improves the text hot path without forcing an all-at-once rewrite of the entire execution plane.
- It preserves the worker boundary, which keeps the control plane free of runtime payload ownership and model-kernel concerns.
- It avoids tying multimodal and tooling expansion to immediate Swift parity across every runtime family.
- It makes the shared worker RPC contract more valuable by allowing different worker implementations to coexist behind one routing layer.

## Rejected Alternatives

### Keep the current Python-heavy execution split unchanged

Rejected because:

- it leaves the latency-critical text path in the same runtime model even when the product is Apple-Silicon-first
- it misses the opportunity to optimize the hottest local generation path without disturbing broader worker functionality

### Embed the text runtime directly inside the Swift control plane

Rejected because:

- it collapses the control-plane/worker boundary
- it mixes long-lived orchestration logic with model execution and payload ownership
- it makes resource isolation, crash containment, and future multi-engine routing harder

### Move toward a Swift-only worker model immediately

Rejected because:

- it would force multimodal and tooling paths to migrate before they are the bottleneck
- it would slow down overall capability expansion without first proving value on the text hot path

## Consequences

- Melix will become a polyglot worker system rather than a Python-only execution plane.
- The repository skeleton needs a dedicated Swift text worker service.
- The phase roadmap needs a new early phase for the Swift text `Generate` hot path.
- Future text-runtime depth work such as `Prefill`, `Decode`, and cache-aware phase scheduling will build on the Swift text worker rather than on the Phase 0 Python text path.
