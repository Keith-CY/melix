# CLI Server Start Shortcut

## Goal

Add a one-command local server start path:

```bash
melix server start "Session Title" --model MODEL_ID --port PORT
```

The positional value is a human-readable server session title. Newly created
sessions continue to receive generated identifiers such as `server-session-1`.

## Behavior

- `melix server start` without shortcut arguments keeps the existing runtime
  start behavior.
- `melix server start TITLE --model MODEL_ID` creates a titled local server
  session when no existing session has the same identifier or title.
- Later shortcut starts reuse an existing session when its identifier or title
  matches the supplied positional value.
- Shortcut starts update the bound model and any supplied listener limits before
  applying gateway configuration and starting the resolved generated session ID.
- Generated server session IDs use the first available `server-session-N`
  identifier rather than relying on the current session count.

## Verification

- Parser coverage for the titled positional argument and shortcut flags.
- Runner coverage for create, reuse, validation errors, and generated ID
  allocation.
- Changed-line Swift coverage for the touched CLI scope must remain at or above
  95 percent.

## Metrics

No runtime performance probe is required. The shortcut composes existing local
state persistence and server start paths; success metrics are parser stability,
correct persisted session state, correct target server session ID, and changed
line coverage.
