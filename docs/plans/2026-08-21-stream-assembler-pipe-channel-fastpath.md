# Stream assembler pipe channel lowercase fast path

## Context

The stream assembler parses Harmony pipe channel headers with
`RequestStreamAssembler._pipe_channel_name()`. The hot PR-scoped parser-mode
probe feeds common lowercase `analysis`, `final`, and `commentary` channel
headers repeatedly. Those headers already match Melix's canonical channel names,
so the parser can avoid the fallback token slice plus `.lower()` copy for this
common ASCII path while preserving the generic mixed-case and leading-whitespace
fallbacks.

## Slice

Add a narrow fast path for lowercase `analysis`, `final`, and `commentary`
headers when the channel name starts at byte zero and is followed by whitespace
or the end of the header. Keep the existing scanner for leading whitespace,
unknown channel names, mixed-case names, and non-standard separators.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`. This
slice keeps its focused `test_command`, `coverage_command`, and `probe_command`
entries and adds this plan file to the probe watch list so the workflow remains
traceable.

## Verification Plan

1. Add a regression test proving known lowercase pipe channels skip the fallback
   `.lower()` copy while preserving existing parser behavior.
2. Run the focused stream assembler tests from the registered probe.
3. Run the registered changed-scope coverage command and confirm coverage is at
   least 95%.
4. Run the registered parser-mode probe locally on Linux and use the PR-scoped
   performance workflow as the merge gate.
