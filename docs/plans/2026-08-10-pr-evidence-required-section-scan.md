# PR Evidence Required-Section Scan Slice

## Scope

This Python-only performance slice narrows `scripts/validate_pr_evidence.py` to
capture only the PR evidence sections enforced by the validator:

- `Plan or Spec`
- `Commands Run`
- `Coverage and Metrics`
- `Known Gaps`

The validator still ignores placeholder text in non-gated template sections such
as `Summary` and `Evidence Checklist`; it just avoids retaining those irrelevant
section bodies while scanning large pull request descriptions.

## Registered Probe

The affected path is covered by PR-scoped probe
`pr-evidence-required-section-scan` in `infra/perf/pr_scoped_probes.json`.

- `test_command` runs the focused PR evidence validator tests and registry
  selection/validation tests.
- `coverage_command` measures the validator, the probe script, and the focused
  tests through `scripts/changed_scope_coverage.py`.
- `probe_command` runs
  `scripts/validate_pr_evidence_required_section_probe.py`, which compares the
  current required-section-only extractor against the prior all-section extractor
  on a synthetic large PR body.

## Success Metrics

The probe records:

- `elapsed_ms_mean` for the current extractor.
- `baseline_elapsed_ms_mean` for the prior all-section extractor.
- `delta_ms_mean` where negative is better.
- `speedup_ratio` where values above 1.0 are better.
- `peak_bytes_mean` for current extraction memory.
- `irrelevant_section_line_count` for probe scale.

## 2026-08-23 follow-up slice: heading-first guard

This Python-only follow-up keeps the same registered
`pr-evidence-required-section-scan` probe and narrows the extractor's per-line
heading detection. Large PR bodies are dominated by ordinary bullet/checklist
content, so `_extract_sections(...)` now checks the first character before
calling `str.startswith("## ")`. Required section capture, non-required section
elision, duplicate required headings, and placeholder validation semantics remain
unchanged.
