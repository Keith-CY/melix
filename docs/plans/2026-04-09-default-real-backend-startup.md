# Default Real Backend Startup

## Goal

Make product and local startup paths default to real model backends instead of deterministic placeholders, while keeping deterministic execution available only when tests or operators opt into it explicitly.

## Scope

- Change startup and packaging defaults from deterministic to real backends.
- Keep explicit deterministic flags and runtime branches intact for unit tests and focused local debugging.
- Update tests that assert default startup behavior.
- Update runbooks that currently present deterministic startup as the default operator path.

## Non-Goals

- Remove deterministic runtimes from the repository.
- Replace all deterministic multimodal test fixtures with live-model coverage.
- Redesign model selection, managed model download, or server-session UX beyond the backend default change.

## Validation

- Python tests covering `scripts/dev_up.py`, launch-agent packaging defaults, Homebrew service defaults, and macOS app-bundle launcher output.
- Focused verification that explicit deterministic inputs still flow through unchanged.
