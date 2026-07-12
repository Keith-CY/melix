# Issue 2605 Response Format Constraint Enforcement

**Issue:** #2605 - Enforce `response_format` `json_schema` with grammar-constrained decoding at the sampler.

**Goal:** Stop silently passing structured-output requests through the Python text worker when the runtime cannot enforce them, wire the first generation-time constraint path for `response_format: {"type":"json_object"}`, and then extend the same sampler boundary to schema-backed `response_format: {"type":"json_schema", ...}` requests.

**Architecture:** Keep the existing Swift gateway parsing and `ExecutionMetadata.ext` contract. The control plane already writes `melix.structured_output.mode`, optional `melix.structured_output.schema_json`, cache scope, and prefill hints. This slice keeps protobuf unchanged and makes the Python worker the enforcement boundary:

- `json_object` requests build a JSON-object logits processor from the loaded tokenizer and pass it to `mlx-lm` `stream_generate` and text `BatchGenerator.insert`.
- `json_schema` requests that include `melix.structured_output.schema_json` compile a supported local JSON Schema subset into a schema-aware logits processor. Unsupported schema features fail closed with typed worker errors before unconstrained generation.
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

## Follow-Up Success Criteria

- Schema-backed `json_schema` requests with supported schemas build and forward a schema-aware logits processor through the same standard stream, session stream, and native text insertion paths used by `json_object`.
- The processor masks invalid object keys, missing required-property close braces, invalid enum/const values, invalid primitive values, and array values outside supported item contracts.
- Worker `Generate` no longer fails supported schema-backed requests before prompt rendering; runtime-level `StructuredOutputConstraintError` remains the typed refusal path for invalid or unsupported schemas.
- Unsupported schema features and malformed schema JSON fail closed with details that include `mode=json_schema`, `enforcement=sampler`, and a stable `reason`.
- Structured-output parser metrics continue to mark schema-backed requests as structured JSON.
- Existing post-hoc Swift validation remains in place as a belt-and-suspenders boundary check.

## Performance Probes

- Add focused unit coverage that inspects `logits_processors` forwarding without running a real model.
- Extend `structured-output-json-object-constraint-cache` or add a paired schema probe so tokenizer vocabulary cache behavior, schema compile cost, and cached-mask cost are visible for schema-backed constraints.
- Gate repeated processor construction so cached tokenizer vocabulary and cached normalized schema compilation avoid unnecessary repeated full-vocabulary decode and schema normalization work.
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

## Out of Scope For The Follow-Up PR

- Swift text worker grammar-constrained sampler support.
- Applying the grammar machinery to `tool_choice: required`.
