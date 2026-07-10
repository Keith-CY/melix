# Issue 1385 Model Policy Catalog Slice

## Goal

Add the first shared text model policy catalog path so model identity aliases can
resolve recommended sampling defaults before request dispatch, and make that
lookup visible in the existing effective-policy receipt.

## Scope

- Add a pure catalog lookup type for text model sampling policies.
- Let `ModelSamplingPolicy` merge imported `generation_config` fields with
  catalog recommendations field by field.
- Preserve request, preset, OCR, and gateway precedence already implemented by
  `TextRequestShaper`.
- Add effective-policy receipt fields for policy lookup status, canonical model
  identity, matched alias, source URL, and request override state.
- Wire HTTP gateway, XPC chat execution, and serving-default summaries through
  the catalog-aware initializer.
- Keep the repository default catalog empty for this slice so existing gateway
  defaults do not drift until source-verified production entries are added in a
  later slice.

## Out Of Scope

- Strict unknown-model rejection.
- New public request fields for recommended-sampling opt-in.
- Benchmark/evaluation export schema changes.
- Desktop or CLI inspection UI.

## Files

- Create `services/control-plane-swift/Sources/Requests/TextModelPolicyCatalog.swift`
  for catalog entries, alias normalization, and lookup results.
- Modify `services/control-plane-swift/Sources/Requests/TextRequestShaper.swift`
  to extend `ModelSamplingPolicy` metadata and pass receipt metadata through
  `ShapedTextRequest`.
- Modify `services/control-plane-swift/Sources/Requests/TextEffectivePolicyReceipt.swift`
  to serialize policy lookup metadata deterministically.
- Modify `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
  only if shaped request construction or dispatch metadata needs the new fields.
- Modify `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`,
  `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`,
  and `services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayServingDefaultsStore.swift`
  to use catalog-aware `ModelSamplingPolicy` construction.
- Modify `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`
  with red tests for alias lookup, request override reporting, and unknown
  fallback receipt metadata.

## TDD Steps

1. Add a failing `TextEndpointContractTests` case for a custom catalog entry
   matched by an imported filename alias. Assert effective temperature, `top_p`,
   max tokens, `policy_lookup_status == "known"`, canonical ID, matched alias,
   source URL, and `request_override_applied == false`.
2. Run:

   ```bash
   xcrun swift test --package-path services/control-plane-swift --filter 'TextEndpointContractTests/chatTranslationUsesCatalogSamplingPolicyForAliasedModelIdentity'
   ```

   Expected before implementation: compile failure or test failure because the
   catalog API and receipt fields do not exist.

3. Implement `TextModelPolicyCatalog` and catalog-aware `ModelSamplingPolicy`
   with generation-config precedence over catalog values and catalog fallback
   for missing fields.
4. Add the receipt fields to `ShapedTextRequest` and
   `TextEffectivePolicyReceipt`.
5. Run the same focused test and keep iterating until it passes.
6. Add a failing override test proving request temperature records
   `policy_lookup_status == "operator_override"` while catalog `top_p` and max
   tokens remain effective.
7. Implement the minimal override-status derivation.
8. Add a failing unknown fallback test proving gateway defaults still dispatch
   with `policy_lookup_status == "unknown"`.
9. Implement the minimal unknown metadata defaults.
10. Wire production call sites to use the catalog-aware initializer.
11. Run focused and changed-scope verification:

    ```bash
    xcrun swift test --package-path services/control-plane-swift --filter ControlPlaneTests.TextEndpointContractTests
    ```

12. Build changed-line coverage and scoped metrics before commit/PR.

## Metrics And Verification

- Required changed-line coverage for touched Swift scope: at least 95 percent.
- Focused Swift test suite: `ControlPlaneTests.TextEndpointContractTests`.
- Metrics report: scoped performance report or `N/A` only if no scoped probe
  applies to this request-shaping metadata change.
