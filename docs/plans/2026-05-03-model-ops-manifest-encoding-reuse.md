# Model ops manifest encoding reuse

## Scope

Optimize the registered Python model-ops bundle path by reusing the converged manifest JSON encoding for the final disk write in both conversion and quantization bundle pipelines.

## Rationale

The model-ops bundle pipelines compute `manifest_bytes` by repeatedly encoding the manifest payload until the embedded byte count converges. Before this slice, the final write encoded the already-converged payload again. Reusing the converged bytes removes one redundant JSON serialization per generated bundle while preserving the manifest payload and byte-count semantics.

## Probe

Registered probe: `model-ops-bundle-artifact-byte-accounting` in `infra/perf/pr_scoped_probes.json`.

The probe exercises both `ConvertModel` conversion and quantization paths and reports:

- `elapsed_ms_mean` (lower is better)
- `bundle_scandir_calls_mean` (lower is better; must stay at zero)

## Success Criteria

- Conversion and quantization manifests are still written once after in-memory byte convergence.
- `manifest_bytes` equals the persisted manifest size.
- Artifact byte accounting continues to avoid rescanning bundle directories.
- Registered local probe shows no regression and preferably lower `elapsed_ms_mean`.
