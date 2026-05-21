# Changed-scope diff hunk start parser slice

## Scope

This Python-only performance slice targets the hot hunk-header path in
`scripts/changed_scope_coverage.py` used by changed-scope coverage reporting.
The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`,
which includes focused `test_command`, `coverage_command`, and `probe_command`
entries.

## Change

Replace the per-character numeric accumulation used to parse the new-file start
line in unified diff hunk headers with delimiter lookup plus direct integer
conversion, and route blank context lines through a dedicated branch so the hot
parser avoids constructing a synthetic empty first-character sentinel on every
line. The parser still accepts both `+N,M` and `+N` hunk ranges and keeps
malformed hunk headers non-measurable.

## Verification

Run the registered focused tests, changed-scope coverage command, and local
registered probe on Linux before opening the PR. No Swift runtime behavior is
changed or claimed in this slice.
