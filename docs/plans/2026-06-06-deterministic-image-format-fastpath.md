# Deterministic Image Format Fast Path

## Context

The deterministic image runtime normalizes response formats for each generated or edited image request. Registered PR-scoped probe `deterministic-image-output-byte-accounting` already covers this path with focused tests, changed-scope coverage, and a command-json probe.

## Slice

This performance slice keeps image format semantics unchanged while moving the supported-format membership container out of `_normalized_format()` and into a module-level constant. The goal is to avoid rebuilding the same set literal on every normalization call.

## Validation

- Focused tests: registered probe `test_command` for deterministic image output byte accounting.
- Coverage: registered probe `coverage_command` for the deterministic image runtime/test/probe scope.
- Metrics: registered probe `probe_command`, comparing local baseline against the optimized branch on Linux.

## Boundaries

This is a Python-only slice and is locally verifiable on Linux. It does not change protocol schemas, generated protobuf outputs, or Swift/macOS runtime behavior.
