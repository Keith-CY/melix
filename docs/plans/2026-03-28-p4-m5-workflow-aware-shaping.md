# P4-M5 Workflow-Aware Shaping

## Goal

Make preset selection, workflow metadata, and request shaping explicit control-plane behavior so equivalent logical sessions behave consistently across chat, completions, responses, and messages.

## Scope

- `services/control-plane-swift/Sources/Requests/*`
- `services/control-plane-swift/Sources/HTTPGateway/OpenAI/*`
- `services/control-plane-swift/Sources/Metrics/*`
- `services/control-plane-swift/Tests/ControlPlaneTests/*`
- `services/control-plane-swift/Tests/HTTPGatewayTests/*`
- `docs/README.md`

## Non-Goals

- Add new worker-side execution modes or endpoint-specific worker routes.
- Implement the control-plane preset command family.
- Change session-graph ownership or cache restore logic.
- Add desktop foundation work.

## Design

- Introduce a control-plane `TextRequestShaper` that applies deterministic shaping before worker translation.
- Extend endpoint request contracts with optional `preset_id`, `workflow`, `workflow_run_id`, and `workflow_node_id`.
- Keep precedence explicit:
  - request-provided fields override preset defaults
  - preset defaults override workflow defaults
  - workflow defaults override baseline translator defaults
- Preserve session and branch continuity across endpoint variants by shaping the same logical request into the same worker identity, scheduling, and cache policy metadata.
- Record shaping observability in the HTTP gateway.

## Performance Probes

- `http.shaping_ms`
- `http.preset_shaped_count`
- `http.workflow_shaped_count`

## Work Steps

1. Add failing contract tests for preset and workflow fields across endpoint request shapes.
2. Add failing translation tests proving equivalent endpoint requests shape into the same worker request metadata.
3. Implement `TextRequestShaper` and route all text endpoints through the same normalize -> shape -> translate path.
4. Record shaping metrics in the HTTP gateway and add handler-level verification.
5. Run focused Swift tests, Python tests, integration tests, touched-line coverage, and diff check.

## Verification

```bash
swift test --package-path services/control-plane-swift --filter '(TextEndpointContractTests|OpenAIHandlerTests)'
make py-test
make integration-test
/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swift test --package-path services/control-plane-swift --scratch-path /tmp/melix-control-plane-p4m5-coverage --enable-code-coverage --filter '(TextEndpointContractTests|OpenAIHandlerTests)'
python3 scripts/swift_changed_line_coverage.py --binary /tmp/melix-control-plane-p4m5-coverage/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata /tmp/melix-control-plane-p4m5-coverage/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift services/control-plane-swift/Sources/Requests/TextRequestShaper.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/Metrics/MetricsStore.swift
git diff --check
```

## Acceptance

- Every text endpoint accepts the same preset and workflow metadata vocabulary.
- Equivalent logical sessions shape into consistent worker request metadata regardless of endpoint.
- Request shaping precedence is explicit and test-covered.
- Touched control-plane source stays at or above `95%` changed-line coverage.
- Metrics report includes shaping latency and preset/workflow shaping counts or an explicit `N/A` reason.
