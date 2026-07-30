# Issue 2605 Response Format Constraint Enforcement

**Issue:** #2605 - Enforce `response_format` `json_schema` with grammar-constrained decoding at the sampler.

**Goal:** Stop silently passing structured-output requests through the Python text worker when the runtime cannot enforce them, wire the first generation-time constraint path for `response_format: {"type":"json_object"}`, and then extend the same sampler boundary to schema-backed `response_format: {"type":"json_schema", ...}` requests.

**Architecture:** Keep the existing Swift gateway parsing and `ExecutionMetadata.ext` contract. The control plane already writes `melix.structured_output.mode`, optional `melix.structured_output.schema_json`, cache scope, and prefill hints. This slice keeps protobuf unchanged and makes the Python worker the enforcement boundary:

- `json_object` requests build a JSON-object logits processor from the loaded tokenizer and pass it to `mlx-lm` `stream_generate` and text `BatchGenerator.insert`.
- Continuous batches retain the locked `mlx-lm` per-sequence processor list and filter it by the same kept indices as UIDs, tokens, and state machines. A mixed constrained/unconstrained regression covers successive completed-row filters through the Melix MTP wrapper.
- `json_schema` requests that include `melix.structured_output.schema_json` compile a supported local JSON Schema subset into a schema-aware logits processor. Unsupported schema features fail closed with typed worker errors before unconstrained generation.
- Required and named tool choices compile the declared tool schemas through the same bounded schema compiler. Shared compiler failures are remapped at the tool boundary to `mode=tool_choice` with stable invalid, unsupported, or complexity reasons while retaining schema pointers and limits. Non-reasoning requests start at a shared tool-wire trigger at token zero; reasoning-enabled routes fail closed until a bounded reasoning-prefix policy is available.
- Tool definitions that omit `parameters` or carry the normalized empty object use an explicit object schema at the worker boundary, so valid parameterless required and named functions remain enforceable and emit `{}` arguments.
- `ToolWireGrammarDescriptor` is shared across the Swift parser registry and worker metadata. JSON-object arguments and XML parameter blocks use parser-round-trippable descriptors with explicit begin, end, trigger, sentinel-token, and argument-style fields.
- Worker descriptor admission strictly parses the control-plane sentinel-token JSON and accepts it only when the ordered token tuple exactly matches the selected wire dialect. Explicit dialect, argument-style, begin, end, and trigger fields must also match that fixed descriptor. Malformed, duplicate, oversized, or mismatched descriptors fail closed with stable typed reasons before grammar construction.
- `MLXTextRuntime` treats sampler enforcement as an explicit backend capability. `AutoMLXBackend` declares that capability and performs its API-specific checks; any other backend must opt in explicitly or receive a typed `backend_sampler_constraints_unsupported` refusal before generation.
- Legacy internal parser-context requests that only set `melix.structured_output.mode=json_schema` without schema payload remain parser-context-only so current tool-parser tests and non-OpenAI internal paths are not reclassified as enforceable schema requests.

**Tech Stack:** Python 3.12, `mlx-lm` 0.31.3 `logits_processors`, MLX worker `EngineCore`, `AutoMLXBackend`, `RequestStreamAssembler`, existing worker protobuf `ExecutionMetadata.ext`, pytest.

## Current Evidence

- `OpenAIHandler` parses malformed `response_format` payloads and maps `StructuredOutputFormatError` to typed invalid-request responses.
- `ChatRequestTranslator` serializes structured output into `ExecutionMetadata.ext` keys and cache scope.
- `RequestCoordinator` validates completed text post-hoc with `StructuredOutputValidator`.
- Python `EngineCore` passes `execution.ext` into the text runtime and uses `RequestStreamAssembler` for parser context, but the MLX generation path does not pass structured-output logits processors.
- Local `mlx-lm` 0.31.3 exposes `generate_step(..., logits_processors=...)`, `BatchGenerator(..., logits_processors=...)`, and `BatchGenerator.insert(..., logits_processors=...)`.

## Completed In PR #2768

- `json_object` requests reaching `AutoMLXBackend.generate_tokens()` pass a JSON-object constraint processor to `stream_generate`.
- Native text `BatchGenerator.insert()` receives the same per-sequence processor list for constrained JSON-object requests.
- Native text `BatchGenerator.insert()` fails closed with `StructuredOutputConstraintError` when the installed `mlx-lm` API cannot accept `logits_processors`.
- The native MTP path passes supported processors and fails closed when the batched API cannot enforce them.
- Worker `Generate` returns a typed error for schema-backed `json_schema` requests while schema grammar compilation is unavailable.
- Structured-output parser metrics still identify JSON-only requests as `structured_json`.

## Follow-Up Scope For Full Schema Enforcement

The next slice keeps the same worker-side enforcement boundary and replaces the temporary schema-backed refusal with a local compiler for the JSON Schema subset Melix can enforce exactly at token level:

- Root schema must resolve to an `object`.
- Supported schema keywords: `type`, `properties`, `required`, `additionalProperties`, `items`, `enum`, `const`, `minimum`, `maximum`, `minItems`, and `maxItems`.
- Supported primitive types: `object`, `array`, `string`, `integer`, `number`, `boolean`, and `null`.
- Supported unions are explicit `type` arrays containing the primitive types above.
- Unsupported keywords such as `$ref`, `oneOf`, `anyOf`, `allOf`, `patternProperties`, string regex constraints, and conditional schemas fail closed with `unsupported_structured_output` and a machine-readable reason instead of falling back to unconstrained generation.
- Legacy internal parser-context requests that only set `melix.structured_output.mode=json_schema` without schema payload remain parser-context-only.

### Compiler and Runtime Bounds

Client-provided schemas are admitted through an explicitly bounded compiler path. The implementation rejects schemas larger than 64 KiB, deeper than 32 schema nodes, or containing more than 1,024 compiled nodes. Per-node collections are capped at 256 properties, 256 required names, 1,024 array items, and 1,024 enum values, with enum payload text capped at 32 KiB. The array-item bound is checked while values are still `Decimal`, before any potentially expansive integer conversion. Schema and tool compilation share a 50 ms admission budget whose deadline is checked inside recursive node compilation and high-cost property, enum, structural-candidate, and fixed-trie loops, so one complex schema cannot evade an outer tool-loop check. Rejections use typed `json_schema_too_complex` or `tool_schema_too_complex` details before tokenizer vocabulary scanning or generation starts.

Compiled enum values carry immutable prefix indexes so fixed-value transitions are constant-time rather than scanning every enum candidate for every tokenizer token. Compiled schema nodes use identity hashing, request-owned processor mask caches are bounded, and unconstrained string values do not accumulate their full text in automaton state. Global schema, tool-definition, tool-prefix-trie, and XML-state caches are bounded by both entry count and conservative retained-graph byte estimates; large client-provided enum, const, or tool-schema graphs evict older entries before the aggregate estimate reaches 16 MiB per cache. These invariants keep mask construction bounded and avoid retaining either one vocabulary-sized mask per generated free-text character or an entry-count-bounded set of unbounded compiled graphs.

Grammar state-space audits are also bounded by explicit state, transition, and wall-clock budgets. This is separate from the single-path request automaton: a diagnostic breadth-first walk can otherwise retain every distinct bounded-number prefix and grow approximately tenfold per digit. Budget exhaustion fails closed with `json_schema_too_complex(limit=state_space_exploration)` instead of continuing an unbounded frontier walk.

The supported subset intentionally rejects duplicate object keys during generation. Numeric schemas accept ordinary JSON decimal and exponent syntax, but every admitted numeric prefix must retain at least one completion satisfying type and range constraints; contradictory ranges and non-finite bounds fail during compilation. A leading minus retains all completions in the negative interval through zero, including negative zero and negative fractions. Schema numbers are parsed as exact `Decimal` values so range admission never passes through binary floating-point normalization. Numeric bounds with exponent magnitudes through 1,024 are supported; bounds beyond that grammar capability fail compilation with `json_schema_too_complex(limit=max_exponent_magnitude)` rather than admitting a schema whose satisfying value cannot be generated.

Enum and const values use an exact Decimal-aware canonical JSON representation. Their finite candidate sets are validated recursively against the compiled node before the fixed-value trie is built. This makes `enum` and `const` a conjunction with every supported keyword at the same node: `type`, `properties`, `required`, `additionalProperties`, `items`, `minItems`, `maxItems`, `minimum`, and `maximum`. Invalid candidates are removed, and a node with no remaining candidate fails compilation with typed `json_schema_unsatisfiable` details rather than generating a value that violates its structural schema.

The shared node for JSON Schema `true` retains unrestricted semantics recursively, including non-empty object values reached through `additionalProperties: true`, property schemas set to `true`, and unrestricted array items. Explicit `null` values for `type`, `properties`, and `required` are invalid rather than aliases for omitted keywords. Enum and const canonicalization, property and required names, tool names, and tool-wire markers all validate UTF-8 encodability; unpaired surrogate values fail with typed details instead of leaking a native encoding exception or compiling an unreachable grammar. Fixed JSON values, object keys, and JSON tool names use canonical ASCII `\u` escapes, including surrogate pairs for non-BMP code points, so tokenizers whose byte-fallback tokens decode individually cannot make valid Unicode constraints unreachable.

Both generic JSON-object and schema-aware numeric grammars admit only the ASCII digits `0` through `9`, as required by JSON. Unicode characters classified as digits are rejected in integer, fraction, and exponent positions before sampling can emit a value that the JSON parser cannot consume.

Once a schema-backed or JSON-object grammar reaches a complete JSON value and the tokenizer exposes EOS, the sampler mask admits EOS only. The underlying acceptance automaton still recognizes trailing JSON whitespace for validation, but generation does not spend additional decode steps producing semantically empty suffixes. Completed non-parallel tool grammars apply the same EOS-only rule; parallel tool grammars retain whitespace separators and the next-call prefix path.

## Follow-Up Success Criteria

- Schema-backed `json_schema` requests with supported schemas build and forward a schema-aware logits processor through the same standard stream, session stream, and native text insertion paths used by `json_object`.
- OpenAI conformance rows cover both schema-valid completed output and the HTTP mapping of a typed worker sampler refusal with structured-output details.
- The processor masks invalid object keys, missing required-property close braces, invalid enum/const values, invalid primitive values, and array values outside supported item contracts.
- Worker `Generate` no longer fails supported schema-backed requests before prompt rendering; runtime-level `StructuredOutputConstraintError` remains the typed refusal path for invalid or unsupported schemas.
- Unsupported schema features and malformed schema JSON fail closed with details that include `mode=json_schema`, `enforcement=sampler`, and a stable `reason`.
- Structured-output parser metrics continue to mark schema-backed requests as structured JSON.
- Required and named tool choices use sampler-enforced JSON or XML wire grammars. Named selection cannot enter another tool's prefix, required selection admits only declared tools, parallel calls preserve whitespace separators, and no prose prefix is accepted for non-reasoning routes.
- JSON and XML tool fixtures round-trip enum, scalar, object, array, required, optional, and string-with-`<` arguments through the rescue/parser boundary.
- XML parameter dialect compilation validates selected function and property names against the same parser regular expressions used by `parse_tool_body`; names that cannot round-trip fail with stable typed reasons before a grammar trie is built. Function and XML parameter names are each limited to 256 UTF-8 bytes so client-controlled trie paths remain explicitly bounded.
- Backends without an explicit sampler-constraint capability fail closed for `json_object`, schema-backed `json_schema`, and required or named tool choices. Schema-less legacy `json_schema` parser context remains unconstrained and backward compatible.
- Every sampler constraint exposes a packed allow-token mask plus `constraint_kind`, `mask_vocab_words`, `fast_path_used`, and `fallback_reason` receipts. `mask_vocab_words` is derived from the tokenizer vocabulary width and highest decoded token ID, so sparse decoded-vocabulary maps cannot under-report the packed mask shape. The current unfused MLX logits-processor path reports `structured_output_acceleration_unsupported` rather than claiming the fused fast path.
- Existing post-hoc Swift validation remains in place as a belt-and-suspenders boundary check.

## Performance Probes

- Add focused unit coverage that inspects `logits_processors` forwarding without running a real model.
- Extend `structured-output-json-object-constraint-cache` or add a paired schema probe so tokenizer vocabulary cache behavior, schema compile cost, and cached-mask cost are visible for schema-backed constraints.
- Gate repeated processor construction so cached tokenizer vocabulary and cached normalized schema compilation avoid unnecessary repeated full-vocabulary decode and schema normalization work.
- Measure cold schema compilation with the compile cache cleared before every sample, pathological-schema refusal latency, enum-prefix mask construction, free-text mask-cache cardinality, and cached schema-mask latency. Cold compile p95 and complexity-limit refusals are hard-gated below 50 ms on the local probe host.
- Measure required/named tool grammar cold compilation with the compile cache cleared before every sample, bounded state-space refusal, packed-mask word count, and JSON/XML grammar/parser round-trip mismatch count. The probe fails when cold tool/schema admission p95 reaches 50 ms rather than reporting cache-hit latency as compile evidence.
- Run a bounded local quantized-model comparison after the resource-bound regression is fixed. The acceptance target is at least 80% of unconstrained greedy tok/s for a small schema with zero invalid outputs; failure remains a blocker or is reported as an external model/runtime blocker with artifacts.
- Use `scripts/structured_output_real_model_probe.py` for that comparison. It accepts only one to three iterations and one to sixteen generated tokens per run, warms both unconstrained generation and the immutable constrained-mask templates, and writes a versioned JSON receipt when `--output` is supplied. Throughput compares only the same minimal const-object fixture. A separate constrained conformance set covers const, enum with optional fields, free text, and nested object/array schemas; every fixture and the warm constrained output must validate against its compiled schema.
- Reuse immutable tokenizer/schema/state mask templates across JSON and tool-grammar requests while retaining request-owned automaton state, applied-token counters, and bounded local mask caches. Immutable tool and XML choice tries are shared only for identical compiled tool sets and descriptors; mask keys also include the parallel policy so distinct grammar contracts cannot collide. This keeps full-vocabulary mask compilation out of steady-state token throughput without allowing one request to mutate another request's grammar state. The shared template cache is limited to both 64 entries and a conservative 64 MiB estimate (`8 bytes/token`, `36 bytes/packed word`, and `4 KiB/entry`); an individual template above that byte cap remains request-local. Compiled schema/tool/trie caches separately use weighted LRU bounds of at most 16 MiB each so cached client-controlled graphs cannot grow with payload size behind a fixed entry count.
- The bounded `mlx-community/Qwen3-0.6B-4bit` v2 run produced `355.98` unconstrained median tok/s and `345.54` constrained median tok/s under the current host load, a `0.9707` ratio, with zero invalid constrained outputs across three measured iterations and zero invalid outputs across the four-fixture conformance set. The probe performs one cold constrained warm-up before both measured series so the constrained series measures the same model with reusable immutable templates populated; the cold constrained run remains in the same receipt and produced a valid output at `19.91` tok/s. The receipt aggregates memory across warmups, benchmark runs, and conformance fixtures and records a `0.39694 GB` peak. This separates first-request mask compilation from warmed steady-state decode instead of hiding it. The local receipt is `.runtime/issue-2605-qwen3-real-model-probe.json`.
- Report the focused pytest commands and metrics in PR evidence. Full pre-commit gates remain required before merge on this host.

## Implementation Steps

1. Add red worker tests:
   - `json_schema` with schema payload emits a typed `unsupported_structured_output` worker error.
   - `json_object` forwards a grammar/logits processor to `stream_generate`.
   - Native text `BatchGenerator.insert()` receives a per-sequence processor list for `json_object`.
2. Implement a small `worker.runtime.structured_output_constraints` module:
   - request-mode normalization from `ExecutionMetadata.ext`;
   - typed `StructuredOutputConstraintError`;
   - JSON-object prefix automaton and logits processor;
   - tokenizer vocabulary decoding, EOS handling, and single-sequence input guards.
3. Wire `AutoMLXBackend`:
   - cache whether `stream_generate` accepts `logits_processors`;
   - pass processors on the standard no-session and session paths;
   - pass processors into native text `BatchGenerator.insert` only when the installed API accepts them.
4. Wire `EngineCore` typed refusal:
   - fail closed before prompt rendering for schema-backed `json_schema`;
   - include details for `mode`, `enforcement`, and `reason`.
5. Verify focused Python tests, then run the relevant Melix Python test gate and PR-scoped metrics.

## Follow-Up Implementation Steps

1. Add red worker tests for a supported schema-backed request:
   - schema processor construction returns a logits processor instead of raising the temporary schema-unavailable worker error;
   - required object keys are enforced;
   - enum/const values are enforced;
   - unsupported schema keywords fail closed with a stable reason.
2. Add red backend tests proving supported schema processors are forwarded to standard `stream_generate`, session `stream_generate`, and native text `BatchGenerator.insert`.
3. Add a red `Generate` service test proving supported schema-backed requests are not rejected by `EngineCore` before runtime generation.
4. Implement schema parsing and normalization inside `worker.runtime.structured_output_constraints` with explicit supported-keyword validation and typed refusal details.
5. Replace the generic JSON-object-only prefix automaton with a schema-aware variant for `json_schema`, reusing tokenizer vocabulary caching and mask caching.
6. Update or add the PR-scoped performance probe to capture schema compile and mask-cache metrics.
7. Run focused tests, changed-scope coverage, full local gates, and the scoped performance report before opening the PR.

## Remaining Out of Scope

- Swift text worker grammar-constrained sampler support.
- A fused MLX/Metal packed-mask consumer. Until that runtime path exists, constrained requests remain correct on the logits-processor path and emit the typed acceleration fallback receipt.

## Completion Verification

- The completed Python-worker implementation is integrated with `origin/main` at `0f555b919ffe7e8cdc77b52f28fa2451f7da196d`.
- Post-integration structured-output, tool-registry, and runtime-utils tests pass together (`315 passed`).
- The final pre-commit transaction must rerun `make swift-test`, `make py-test`, `make integration-test`, and the current-base PR-scoped performance report before PR handoff.
- Direct changed-scope coverage must remain at or above 95 percent for the structured-output and adjacent MLX text paths, with zero direct or gated performance regressions.
- The only deferred implementation remains the Swift text-worker sampler and the fused MLX/Metal packed-mask consumer described above.
