# Hub catalog direct size hint split elision

## Slice

Optimize the registered `hub-catalog-size-hint-regex-precompile` Python hot path by removing the fallback `str.split(maxsplit=2)` allocation in `_direct_size_hint_from_text`.

## Probe coverage

The affected path is already covered by the PR-scoped registered probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`, including focused `test_command`, `coverage_command`, and `probe_command` entries.

## Behavior contract

Direct size hints continue to accept two-token values with surrounding or repeated whitespace, for example `12 GB`, `12\tGB`, and `  12   GB  `. Inputs with extra non-whitespace tokens such as `12 GB extra` still fall back as invalid for the direct parser.

## Verification plan

- Run focused hub catalog tests and the registered probe test.
- Run changed-scope coverage through the registered probe coverage command.
- Run `scripts/hub_catalog_size_hint_probe.py` locally on Linux for before/after metrics.
