# Retrieval store complete-record fast path

## Scope

This Python-only performance slice is limited to
`worker.runtime.retrieval_context.project_retrieval_store_records(...)`.
The hot path receives exact `dict` records from retrieval lookup storage with
all prompt-context metadata already present and valid. The previous store
projection still constructed a `RetrievalContextEntry` and then a
`PromptContextAdmission` for every valid record before copying the single
admission receipt into the projection output.

## Registered PR-scoped probe

The affected path is covered by the existing registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` fields for:

- `services/mlx-worker-python/worker/runtime/retrieval_context.py`
- `services/mlx-worker-python/tests/test_retrieval_context.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/retrieval_context_projection_probe.py`

No probe registry change is required for this slice because the registered probe
already measures store-record projection metrics.

## Optimization slice

Add a narrow fast path for exact `dict` store records whose `context_kind`,
`source_id`, `payload`, `owner_scope_checked`, `segment_id`, `source_field`,
`reason`, and `corrective_action` are already valid. For those complete records,
project the payload and construct the included untrusted-context receipt directly,
avoiding the intermediate `RetrievalContextEntry`, `PromptContextSourceEvidence`,
`PromptContextSegment`, and `PromptContextAdmission` objects.

Records with missing/default metadata, mapping subclasses, malformed values, or
multi-field monkeypatched admissions continue through the existing admission path.
Duplicate `source_field` handling remains unchanged by feeding the direct receipt
through the existing duplicate-refusal helper.

## Verification plan

Run the registered probe commands locally on Linux:

```bash
# Use the exact `test_command` and `coverage_command` from the
# `retrieval-context-projection-fastpath` registry entry.
python3 - <<'PY' > /tmp/retrieval_test_cmd.sh
import json
for probe in json.load(open('infra/perf/pr_scoped_probes.json')):
    if probe.get('id') == 'retrieval-context-projection-fastpath':
        print(probe['test_command'])
PY
bash /tmp/retrieval_test_cmd.sh

python3 - <<'PY' > /tmp/retrieval_cov_cmd.sh
import json
for probe in json.load(open('infra/perf/pr_scoped_probes.json')):
    if probe.get('id') == 'retrieval-context-projection-fastpath':
        print(probe['coverage_command'])
PY
bash /tmp/retrieval_cov_cmd.sh

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id retrieval-context-projection-fastpath --base-repo /path/to/origin-main-worktree --head-repo "$PWD" --output /tmp/retrieval-context-complete-record-fastpath.json
```

The PR-scoped performance workflow remains the merge gate before merging.
