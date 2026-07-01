# Engine Generate Empty Media Usage Fast Path

## Slice

Optimize the Python worker generate hot path for requests that do not produce a
media feature probe. The current implementation constructs the same zero-valued
media usage dictionary for every request before finalization, including the
plain text / `return_usage=false` path covered by the registered
`engine-generate-usage-token-elision` PR-scoped performance probe.

## Scope

- Reuse a module-level zero media-usage mapping when no probe is present.
- Preserve non-empty probe behavior by keeping per-call dictionaries for actual
  media probe counters.
- Keep the existing `engine-generate-usage-token-elision` focused tests,
  changed-scope coverage command, and probe as the validation source.

## Validation

Linux local validation must run the registered probe commands for
`engine-generate-usage-token-elision`:

- focused pytest command from `infra/perf/pr_scoped_probes.json`
- changed-scope coverage command from `infra/perf/pr_scoped_probes.json`
- `scripts/engine_generate_usage_token_probe.py`

CI validation must include the PR-scoped performance workflow and registered
probe report before merge.
