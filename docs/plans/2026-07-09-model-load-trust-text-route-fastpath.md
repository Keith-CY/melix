# Model Load Trust Text Route Fast Path

## Context

The `model-load-config-json-bytes` PR-scoped performance probe exercises repeated
text-runtime trust policy resolution for `config.json` custom-loader detection.
The path already caches config JSON reads by file stat, so hot iterations spend
more time in the surrounding policy assembly.

## Slice

This slice keeps behavior unchanged and avoids a dictionary lookup for the common
`runtime_kind == "text"` default route-class case. Explicit request policy and
model-spec route classes still take precedence. Non-text runtime kinds continue
to use `ROUTE_CLASS_BY_RUNTIME_KIND`.

## Validation

- Focused model-load trust tests cover default route-class behavior and add a
  regression guard that the text default does not query the route map.
- The registered PR-scoped probe remains `model-load-config-json-bytes` in
  `infra/perf/pr_scoped_probes.json`; it already declares focused test,
  coverage, and command-json probe commands for this path.
