# PR Evidence Checklist

Use this checklist before merging or handing off a change.

- Relevant plan or spec is identified.
- Behavior changes are reflected in the relevant docs.
- Protocol changes include regenerated generated artifacts.
- Dependency changes include updated lockfiles.
- Relevant tests were run.
- The affected path has defined performance probes and target metrics.
- Observability mode is identified for the changed path: `off`, `minimal`, `sampled`, `evidence`, or `debug`.
- Probe overhead is recorded for observability changes, or `N/A` is stated explicitly with the reason.
- Deferred debug, sampled, or evidence-mode work is called out instead of hidden in logs or screenshots.
- A metrics report is included, or `N/A` is stated explicitly with the reason.
- Command outcomes are recorded.
- Deferred work and known gaps are stated explicitly.
