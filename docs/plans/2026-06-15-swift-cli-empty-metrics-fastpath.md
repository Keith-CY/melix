# Swift CLI empty metrics fast path

## Scope

Optimize one Swift CLI JSON envelope path: when an envelope caller supplies no
pre-existing metrics, construct the injected metrics dictionary directly instead
of allocating an empty dictionary with reserved capacity and running an empty
copy loop.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`swift-cli-json-envelope-encoding` in `infra/perf/pr_scoped_probes.json`.
The probe watches `Sources/MelixCLICore/MelixCLIJSON.swift` and has focused
`test_command`, `coverage_command`, and `probe_command` entries that run on the
`macos-15` runner.

## Verification boundary

This scheduled slice runs from Linux, where `swift` is not installed, so local
Swift runtime effects are not validated here. The macOS PR-scoped performance
workflow is the source of truth for the Swift performance metric.

## Expected behavior

JSON envelope content stays identical. Only the internal construction path for
empty input metrics changes.
