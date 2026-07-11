# Issue 1385 Strict Recommended Sampling Opt-In Slice

## Goal

Add an explicit request-level opt-in for applying recommended model sampling
policy in strict mode. Strict mode must fail before worker dispatch when the
selected model has no source-backed catalog policy. Non-strict requests keep the
existing fallback behavior and still emit effective-policy receipts.

## End-State Architecture

Per-model sampling policy is a product contract, not an incidental backend
default. The control plane owns the policy decision at request admission:

- request fields capture whether the operator asked Melix to require
  recommended sampling;
- model settings and the shared text model policy catalog resolve policy
  provenance;
- strict admission fails closed before model loading or worker dispatch when the
  catalog lookup is unknown;
- successful requests serialize the opt-in and strictness outcome into the same
  effective-policy receipt family used by chat, benchmark, eval, and diagnostic
  evidence.

This slice implements the API and admission contract for OpenAI chat
completions. Later slices can reuse the same normalized request fields for
benchmark/evaluation exports, CLI inspection, and desktop controls.

## Scope

- Add OpenAI-compatible request fields for recommended sampling opt-in.
- Carry the opt-in through `NormalizedTextRequest`.
- Fail `/v1/chat/completions` with a typed `invalid_argument` response before
  worker dispatch when strict recommended sampling is requested for an unknown
  model policy.
- Preserve existing non-strict behavior: imported `generation_config`, gateway
  serving defaults, and request overrides continue to work without requiring a
  catalog entry.
- Emit effective-policy receipt metadata showing whether recommended sampling
  was required by the request.
- Add tests proving:
  - the new request field decodes and normalizes;
  - strict unknown-model requests return a typed HTTP error and do not dispatch;
  - strict known-model requests dispatch and retain catalog provenance.

## Out Of Scope

- Production source-verified catalog entries.
- Strict policy for `/v1/completions`, `/v1/responses`, or `/v1/messages`.
- Benchmark/evaluation export schema updates.
- CLI or desktop policy inspection controls.
- Automatic application of recommendations without operator opt-in.

## API Contract

OpenAI chat completions accepts a Melix extension field:

```json
{
  "model": "melix-dev-text",
  "messages": [{ "role": "user", "content": "Hello" }],
  "melix_recommended_sampling": "strict"
}
```

Accepted values:

- `null` or omitted: non-strict default; no strict admission gate.
- `false` or `"off"`: explicit non-strict behavior.
- `true`, `"required"`, or `"strict"`: require source-backed recommended
  sampling.

Malformed values fail request schema decoding through the existing OpenAI
invalid-schema response path.

Strict unknown-model failure response:

```json
{
  "error": {
    "code": "invalid_argument",
    "field": "melix_recommended_sampling",
    "phase": "sampling_policy_admission",
    "sampling_policy_error": "unknown_model_policy",
    "model": "<resolved-model-id>",
    "message": "Recommended sampling was required, but Melix has no source-backed policy for the selected model."
  }
}
```

## TDD Steps

1. Add a failing decode/normalize test in
   `TextEndpointContractTests` proving `"melix_recommended_sampling": "strict"`
   becomes a normalized strict request.
2. Add a failing HTTP test in `OpenAIHandlerTests` proving strict unknown-model
   chat requests return the typed 400 error and leave the worker client without
   a generate request.
3. Add a failing translator or HTTP test proving strict known-model requests
   dispatch and keep catalog receipt provenance.
4. Implement the normalized request field and custom request-value decoder.
5. Implement strict sampling admission after model/catalog resolution and before
   on-demand model loading.
6. Extend effective-policy receipts with a request-required flag.
7. Run focused tests and iterate until green.

## Metrics And Verification

- Focused tests:

  ```bash
  xcrun swift test --package-path services/control-plane-swift --filter 'TextEndpointContractTests|OpenAIHandlerTests'
  ```

- Changed-line coverage for touched Swift files must be at least 95 percent.
- Scoped performance report must be `ok` with zero in-scope regressions. This
  slice is request-admission metadata, so selected probes may be zero.
- Before commit on a 128 GiB+ macOS host, run the versioned pre-commit hook,
  which executes `make swift-test`, `make py-test`, `make integration-test`,
  and the scoped performance report.
