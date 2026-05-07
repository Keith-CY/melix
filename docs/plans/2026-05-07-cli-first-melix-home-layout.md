# CLI-First Melix Home Layout

## Goal

Make `MELIX_HOME` the single product-owned filesystem source of truth for Melix
CLI and App surfaces. The macOS App may keep launcher or install metadata under
platform-specific locations when explicitly configured, but product state,
configuration, model receipts, managed models, jobs, runtime packs, and secrets
must default under `MELIX_HOME`.

Compatibility with previous `~/Library/Application Support/Melix` state is out
of scope for this slice. The operator-session split still performs a one-shot
fallback when an existing monolithic `state/operator-session.json` is present
under the resolved `MELIX_HOME` and the new split files do not yet exist, so
server sessions, registry roots, and download queue entries are not discarded
when the split-file layout is first read.

## Target Layout

```text
MELIX_HOME/
  config/
    gateway-config.json
    gateway-serving-defaults.json
    image-defaults.json
    model-roots.json
    remote-servers.json
    server-sessions.json
    evaluation-prompts.json
  state/
    operator-session.json
    download-queue.json
    lora-training-jobs.json
    persistent-auth-sessions.json
  secrets/
    huggingface-token.json
    remote-server-api-keys.json
    server-session-api-keys.json
  models/default-managed/
  runtime-packs/audio/
  jobs/model-ops/
  jobs/evaluation/
  logs/
  run/
  install/
```

The default `MELIX_HOME` is `$HOME/.melix`. `MELIX_APP_SUPPORT_DIR` is not a
core fallback and should not be exported by productization as the primary home.

## Implementation Plan

1. Add a shared Swift path layout in the control-plane core package and make the
   CLI-facing `MelixHome` mirror it.
2. Move control-plane config stores to `MELIX_HOME/config` and
   `MELIX_HOME/state` defaults, while preserving explicit store-path overrides.
3. Split aggregate operator persistence internally so CLI product config
   (`server-sessions`, `model-roots`) no longer lives in the same file as App UI
   session state.
4. Update App, app-bundle, local install, and dev-stack environment generation
   to export `MELIX_HOME` plus derived path overrides rather than App Support
   roots.
5. Keep benchmark export/submission collection aware of the split jobs layout:
   a `jobs/` parent must collect benchmark artifacts from `model-ops/bench` and
   evaluation artifacts from `evaluation`.
6. Update tests and docs that currently assert Application Support defaults.

## Verification

- Focused Swift tests for `MelixHome`, operator persistence, gateway config
  stores, local runtime path injection, and App bootstrap environment.
- Focused Python tests for app bundle env scripts, local install layout, and dev
  stack env generation.
- Repository search must show no default product data root under
  `~/Library/Application Support/Melix`, excluding historical docs or explicit
  App install metadata discussion.
