# Swift CLI Metric Name ASCII Fast Path

## Goal

Reduce JSON envelope metric placeholder construction overhead for the common ASCII metric-name path without changing emitted JSON schema or placeholder token shape.

## Scope

- Affected code path: `Sources/MelixCLICore/MelixCLIJSON.swift`
- Registered PR-scoped probe: `swift-cli-json-envelope-encoding`
- Focused tests: `MelixCLIRunnerTests` JSON envelope and metric-placeholder cases

## Implementation

`MelixCLIJSONMetricPatch.makePlaceholder(metricName:)` previously checked every Unicode scalar through `CharacterSet.alphanumerics`. This slice adds an ASCII-only branch for the common metric-name characters (`A-Z`, `a-z`, `0-9`) and maps other ASCII punctuation to `_` directly. Non-ASCII scalars continue through the existing `CharacterSet.alphanumerics` behavior, preserving compatibility.

## Validation Boundary

This is a Swift/macOS path. The local scheduled Linux worker can inspect and edit the Swift source, but it cannot validate Swift runtime performance effects locally. The registered macOS PR-scoped performance probe (`swift-cli-json-envelope-encoding`) is the source of truth for performance validation before merge.
