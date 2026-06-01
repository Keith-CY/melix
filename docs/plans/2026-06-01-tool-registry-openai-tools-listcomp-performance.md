# Tool Registry OpenAI Tools List Construction Performance Slice

## Scope

This slice optimizes `ToolRegistry.as_openai_tools()` for the built-in agentic
registry. Behavior remains unchanged: each call still returns fresh OpenAI tool
payload dictionaries, nested `parameters.properties` dictionaries, and fresh
`required` lists so callers cannot mutate registry-owned templates.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`tool-registry-openai-tools-template-cache` in
`infra/perf/pr_scoped_probes.json`. The probe runs focused tool-registry tests,
changed-scope coverage, and `scripts/tool_registry_openai_tools_probe.py`, which
checks payload isolation and reports elapsed time plus descriptor-call counts.

## Verification plan

- Run the focused registered probe test command for tool registry behavior and
  PR-scoped probe selection.
- Run the registered changed-scope coverage command.
- Run `scripts/tool_registry_openai_tools_probe.py` locally on Linux and compare
  against the current `origin/main` baseline.
- Rely on GitHub Actions PR-scoped performance workflow for the final registered
  CI probe report before merge.

## Expected outcome

Replacing the manual append loop with a single list comprehension keeps the
same fresh nested payload construction while reducing Python loop overhead in
high-frequency OpenAI tool payload generation.
