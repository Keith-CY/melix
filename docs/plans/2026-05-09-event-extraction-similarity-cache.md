# Event Extraction Similarity Cache Optimization

## Goal

Reduce repeated pure string-preparation work in event extraction alignment on Linux-verifiable Python paths.

## Touched Files

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`

## Constraints

- Python-only slice; no macOS/Swift local verification required.
- Preserve event alignment scores and output schema exactly.
- Keep cached values immutable so direct helper callers cannot mutate shared cache state.

## Performance Probe

Use the existing event extraction alignment scoped probe:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" python scripts/event_extraction_alignment_probe.py
```

Success metric: preserve structural metrics while reducing `elapsed_ms_mean` for repeated lexical similarity comparisons. The registered scoped CI probe is `event-extraction-alignment-accepted-edge-cache`.

## Verification Commands

- Focused pytest for the string-similarity regression test and alignment probe smoke test.
- Changed-scope coverage for touched executable Python lines with `scripts/changed_scope_coverage.py`.
- Local explicit performance probe comparing `origin/main` against branch head for `event-extraction-alignment-accepted-edge-cache`.
- `git diff --check`.
