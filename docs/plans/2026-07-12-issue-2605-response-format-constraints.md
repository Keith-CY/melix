# Issue 2605 Response Format Constraint Enforcement

**Issue:** #2605 - Enforce `response_format` `json_schema` with grammar-constrained decoding at the sampler.

**Goal:** Stop silently passing structured-output requests through the Python text worker when the runtime cannot enforce them, and wire the first generation-time constraint path for `response_format: {"type":"json_object"}`.

**Architecture:** Keep the existing Swift gateway parsing and `ExecutionMetadata.ext` contract. The control plane already writes `melix.structured_output.mode`, optional `melix.structured_output.schema_json`, cache scope, and prefill hints. This slice keeps protobuf unchanged and makes the Python worker the enforcement boundary:

- `json_object` requests build a JSON-object logits processor from the loaded tokenizer and pass it to `mlx-lm` `stream_generate` and text `BatchGenerator.insert`.
- `json_schema` requests that include `melix.structured_output.schema_json` fail closed with a typed worker error until the schema-to-grammar compiler exists.
- Legacy internal parser-context requests that only set `melix.structured_output.mode=json_schema` without schema payload remain parser-context-only so current tool-parser tests and non-OpenAI internal paths are not reclassified as enforceable schema requests.

**Tech Stack:** Python 3.12, `mlx-lm` 0.31.3 `logits_processors`, MLX worker `EngineCore`, `AutoMLXBackend`, `RequestStreamAssembler`, existing worker protobuf `ExecutionMetadata.ext`, pytest.

## Current Evidence

- `OpenAIHandler` parses malformed `response_format` payloads and maps `StructuredOutputFormatError` to typed invalid-request responses.
- `ChatRequestTranslator` serializes structured output into `ExecutionMetadata.ext` keys and cache scope.
- `RequestCoordinator` validates completed text post-hoc with `StructuredOutputValidator`.
- Python `EngineCore` passes `execution.ext` into the text runtime and uses `RequestStreamAssembler` for parser context, but the MLX generation path does not pass structured-output logits processors.
- Local `mlx-lm` 0.31.3 exposes `generate_step(..., logits_processors=...)`, `BatchGenerator(..., logits_processors=...)`, and `BatchGenerator.insert(..., logits_processors=...)`.

## Success Criteria

- `json_object` requests reaching `AutoMLXBackend.generate_tokens()` pass a JSON-object constraint processor to `stream_generate`.
- Native text `BatchGenerator.insert()` receives the same per-sequence processor list for constrained JSON-object requests.
- Native text `BatchGenerator.insert()` fails closed with `StructuredOutputConstraintError` when the installed `mlx-lm` API cannot accept `logits_processors`.
- The native MTP patch continues to avoid MTP when grammar processors are active.
- Worker `Generate` returns a typed error for schema-backed `json_schema` requests instead of rendering a prompt and generating unconstrained text.
- Structured-output parser metrics still identify JSON-only requests as `structured_json`.
- Existing post-hoc Swift validation remains in place as a belt-and-suspenders boundary check.

## Performance Probes

- Add focused unit coverage that inspects `logits_processors` forwarding without running a real model.
- Register `structured-output-json-object-constraint-cache` to measure tokenizer vocabulary cache behavior and cached-mask cost for the JSON-object constraint helper.
- Gate `build_second_decode_calls_mean` so repeated processor construction does not rescan the full tokenizer vocabulary for the same loaded tokenizer.
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

## Out of Scope For This PR

- Full JSON Schema to grammar compilation.
- Swift text worker grammar-constrained sampler support.
- Applying the grammar machinery to `tool_choice: required`.
