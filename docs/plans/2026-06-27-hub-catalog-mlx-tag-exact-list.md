# Hub Catalog MLX Tag Exact-List Fast Path

## Context

The Hub catalog filters Hugging Face model payloads for MLX compatibility during
search and card summarization. The registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` already covers this path and reports the
`payload_compatibility_elapsed_ms_mean` metric alongside the size-hint metrics.

## Slice

Optimize only the MLX tag payload check by adding an exact built-in `list` path
before the generic list-subclass fallback. Hub API payloads arrive as plain Python
lists after JSON decoding, so the hot path can avoid the slower `isinstance`
checks while preserving subclass semantics for tests and defensive callers.

## Verification

- Focused hub catalog tests for MLX compatibility and registered probe selection.
- Changed-scope coverage through the registered probe `coverage_command`.
- Registered probe command on Linux, using
  `payload_compatibility_elapsed_ms_mean` as the targeted metric.

## Boundary

This is a Python-only Linux-verifiable slice. It does not change Swift code or
protocol-generated artifacts.
