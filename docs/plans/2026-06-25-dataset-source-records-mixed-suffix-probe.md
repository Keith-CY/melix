# Dataset source records mixed suffix probe

## Scope

This Python-only performance slice is limited to the registered PR-scoped probe
for dataset source record ingestion:

- `scripts/dataset_source_records_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

No production ingest behavior changes are included in this slice.

## Registered Probe

The registered PR-scoped performance probe is `dataset-source-records-scandir` in
`infra/perf/pr_scoped_probes.json`. This slice expands its fixture from a
text-only source tree to a mixed lowercase suffix tree (`.txt`, `.md`, `.py`,
`.jsonl`) and clears the source-kind basename cache before each measured
classification sample so future source-kind classifier optimizations are
measured instead of hidden by repeated basename cache hits. The probe precomputes
the full expected source-kind sequence outside the measured loop and uses eleven
samples by default to reduce p95 sensitivity to a single noisy classifier pass.

## Rationale

A local lowercase suffix fast-path experiment did not produce a stable
improvement while the old probe was dominated by repeated cached `.txt` basename
lookups. Before changing production classifier behavior, the registered probe
must measure the intended suffix-classification work directly.

## Verification

Required local verification for this probe-registration slice:

- focused dataset source records PR-scoped probe tests
- changed-scope coverage for the modified tests and probe script
- registered `dataset-source-records-scandir` probe on Linux

## Metrics

The primary metric remains `source_kind_elapsed_ms_mean`; lower is better. The
probe now also reports `source_kind_variant_count=4` so reports show the mixed
suffix fixture is active.

## Known Gaps

This is a Linux-local Python probe slice. It does not validate Swift runtime
effects and intentionally does not claim a production performance speedup.
