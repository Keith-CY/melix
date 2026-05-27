# Manual Main App Packaging CI Plan

## Goal

Allow operators to manually package the self-contained Melix macOS app from the
`main` branch and make the resulting archive easy to download from the GitHub
Actions run.

## Scope

- Update `.github/workflows/package-self-contained-app.yml`.
- Keep the existing pull-request `package-app` label gate unchanged.
- Keep tag release attachment behavior unchanged.
- Add focused regression coverage for the workflow contract.
- Document the manual packaging path in the packaging runbook.

## Design

The existing `package-self-contained-app` workflow remains the single packaging
entry point. `workflow_dispatch` gets an explicit source-ref input that defaults
to `main`, so a manual run packages `main` unless the operator intentionally
overrides it. Manual runs use a dedicated checkout step for the selected source
ref and pass that ref into shell steps through environment variables before
resolving branch or tag build metadata. Push, pull request, and tag runs keep the
default event checkout behavior.

After uploading the app archive, the workflow writes a GitHub Actions step
summary with the artifact name, direct artifact URL when available, and workflow
run URL. Pull requests keep their sticky artifact comment.

## Verification

- Focused Python tests assert the workflow exposes the manual `main` default,
  keeps event checkout behavior for non-manual runs, grants artifact-read
  permissions, and publishes a download summary.
- The change is workflow and documentation only; coverage metrics are `N/A`
  because no executable Melix runtime code path changes.
