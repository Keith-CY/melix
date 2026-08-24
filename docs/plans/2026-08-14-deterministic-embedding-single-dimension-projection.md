# Deterministic embedding single-dimension projection fast path

## Scope

This Python performance slice is limited to
`worker.runtime.embedding_backends.DeterministicEmbeddingBackend._project_digest`
when callers request a one-dimensional deterministic embedding projection.

The one-dimensional path only needs the sign of the first digest word. It can
avoid materializing and normalizing the full eight-word base vector used by the
default and expanded projection paths.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`deterministic-embedding-project-digest-allocation` in
`infra/perf/pr_scoped_probes.json`. The probe already records the focused
single-dimension metric:

- `single_dimension_elapsed_ms_mean`
- `single_dimension_peak_bytes_mean`

The same probe also keeps the default eight-dimension and expanded 4097-dimension
metrics in scope so the fast path does not regress the adjacent projection
branches.

## Verification Plan

1. Add regression coverage proving single-dimension projection reads only the
   first unpacked digest word and does not iterate the full digest sequence.
2. Run the registered focused test command locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally and compare `single_dimension_elapsed_ms_mean`
   against the pre-change baseline.
5. Let GitHub Actions run the registered PR-scoped performance workflow before
   merge.

## Expected Impact

One-dimensional deterministic fixture embedding projections should allocate less
temporary data and run faster. Multi-dimensional projections intentionally keep
the existing base-vector flow and output values.

## Follow-up Slice: First-word digest unpack

The 2026-08-24 follow-up slice keeps the same registered probe and narrows the
implementation to the one-dimensional branch. That branch now unpacks only the
first `uint32` digest word with a dedicated struct unpacker instead of unpacking
all eight words and then reading index zero. Expanded and default eight-
dimensional projections continue using the full eight-word unpacker and preserve
output parity.

Expected impact for this follow-up is lower `single_dimension_elapsed_ms_mean`
and stable or lower `single_dimension_peak_bytes_mean` while preserving the
expanded and default eight-dimensional metrics reported by the probe.
