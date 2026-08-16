# Model registry plain child path construction deferral slice

This Python performance slice is limited to the plain-local root tree scanner in
`worker.model_registry.catalog.WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(...)`.

## Registered probe

The affected path is covered by the PR-scoped registered probe
`model-registry-plain-local-manifest-stat-elision` in
`infra/perf/pr_scoped_probes.json`. This slice retargets that existing model
registry catalog probe to the plain-child path construction metric while keeping
focused `test_command`, `coverage_command`, and `probe_command` entries.

The probe exercises a synthetic plain-local registry with 400 model directories
and 400 manifest-only directories, measuring catalog scan elapsed time and root
plain-child `Path.__truediv__` joins. The root plain-child join metric is the
primary validation point for this slice because it directly counts the deferred
path construction removed from the scan loop.

## Implementation plan

1. Preserve descriptor detection, HF cache repository discovery, and scan order.
2. Avoid constructing a `Path` object for every non-HF plain child directory
   during the root `os.scandir(...)` pass; defer the `Path` join until the
   child is actually pushed onto the traversal stack.
3. Add a focused regression test that counts root plain-child path joins and
   proves plain child directories only join once for stack traversal.
4. Run the registered local test command, changed-scope coverage, and registered
   PR-scoped performance probe on Linux; GitHub Actions remains the merge gate.

## 2026-07-17 follow-up: scandir entry-path traversal

This follow-up keeps the same Python-only scanner boundary and registered
`model-registry-plain-local-manifest-stat-elision` probe. The scanner now stores
`os.DirEntry.path` while collecting child directories and converts that path text
into `Path` objects when pushing traversal stack entries. HF cache repository
detection uses the same entry-path text. This preserves descriptor detection,
root pruning, HF cache detection, and traversal ordering while eliminating the
remaining root-child `Path.__truediv__` joins measured by the probe.

## 2026-08-16 follow-up: direct child regular-file containment fast path

This follow-up stays within the same registered model registry probe boundary and
is limited to `_artifact_embedding_regular_file(...)`, which is exercised by the
artifact embedding metadata checks in the model registry probe. Direct child
artifact files such as `config.json` can be accepted with the existing `lstat()`
regular-file check without first constructing a relative path via
`Path.relative_to(...)`. Nested module config paths continue through the original
containment walk, preserving symlink-directory rejection and out-of-root refusal.

## Verification commands

The full focused test, coverage, and probe commands live in the registered probe
entry so CI and local runs use the same command text:

```bash
python3 -m json.tool infra/perf/pr_scoped_probes.json >/tmp/melix_probes_json_ok
python3 - <<'PY' > /tmp/melix_model_registry_test_command.sh
import json
p=json.load(open('infra/perf/pr_scoped_probes.json'))
probe=next(x for x in p if x['id']=='model-registry-plain-local-manifest-stat-elision')
print(probe['test_command'])
PY
bash /tmp/melix_model_registry_test_command.sh
python3 - <<'PY' > /tmp/melix_model_registry_coverage_command.sh
import json
p=json.load(open('infra/perf/pr_scoped_probes.json'))
probe=next(x for x in p if x['id']=='model-registry-plain-local-manifest-stat-elision')
print(probe['coverage_command'])
PY
bash /tmp/melix_model_registry_coverage_command.sh
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id model-registry-plain-local-manifest-stat-elision --base-repo /root/.hermes/profiles/coder/workspace/worktrees/melix-baseline-model-registry-plain-child-20260717 --head-repo "$PWD" --output /tmp/model-registry-plain-child-path-deferral-pr-scope.json
```
