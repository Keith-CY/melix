# M10-M15 Executable Goals

This document decomposes the `M10.1-M15.4` roadmap slices into concrete execution goals that can be assigned, tracked, and verified without rediscovering intent from the parent roadmap documents.

The goals below are intentionally short and action-oriented. They are not a replacement for the underlying plan documents. They are the next granularity layer for execution sequencing.

## M10 Session Lifecycle And Power Management

### M10.1 Session State Protocol And Snapshots

- Add typed session lifecycle fields to the control-plane protocol, including `loading`, `ready`, `paused`, `sleeping`, and `stopped`.
- Extend snapshots and subscription events with power-state metadata such as idle timers and wake reason.
- Add protocol and hydration tests proving the new state model survives XPC and snapshot refresh paths.

### M10.2 Power Policy And Lifecycle Controls

- Implement control-plane commands for pause, resume, stop, and wake.
- Add idle-timer policy handling for `auto_sleep`, `light_sleep_after`, and `deep_sleep_after`.
- Record lifecycle transition metrics and rejection paths for invalid transitions.

### M10.3 Desktop Status Banners And Operator Surfaces

- Render session-state banners in the desktop shell and chat-facing views.
- Expose operator controls for lifecycle and power policy where supported.
- Add view-model and UI tests proving banner visibility tracks live control-plane state.

### M10.4 Session Lifecycle Integration Evidence

- Add live integration coverage for idle-to-sleep, pause-to-resume, and stop-to-ready flows.
- Produce a metrics report covering start, sleep, wake, and pause latencies.
- Add runbook steps for diagnosing stale state, bad wake behavior, and lifecycle mismatch.

## M11 Disk Streaming, Memory Budgeting, And Cache Policy

### M11.1 Disk Streaming Mode And Runtime Flags

- Add a session-level disk-streaming mode to control-plane and runtime settings.
- Carry the mode through bootstrap, request routing, and operator-visible settings.
- Add tests proving unsupported runtimes fail explicitly when disk streaming is requested.

### M11.2 Memory Budget Admission And Safety Guards

- Add a virtual-memory budget input to load-admission and runtime safety checks.
- Reject unsafe large-model loads before they destabilize memory residency.
- Export memory-budget metrics and integration cases for acceptance and rejection paths.

### M11.3 Streaming Cache Compatibility And Settings Surface

- Define which cache tiers remain valid under disk streaming and how incompatible tiers degrade.
- Expose cache memory, size, and directory controls in settings and effective-state views.
- Add settings-merge coverage showing the final policy after defaults, files, and overrides are resolved.

### M11.4 Large-Model Streaming Benchmarks And Runbooks

- Add streamed-session benchmarks for load time, restore latency, and steady-state throughput.
- Compare RAM-resident and SSD-backed paths using the same model and prompt class.
- Document operator setup, budget tuning, and recovery steps for large-model streaming.

## M12 Model Registry, Family Coverage, And Model Tools

### M12.1 Multi-Root Registry Management And Rescan

- Add explicit add, remove, reorder, and rescan behavior for model roots.
- Preserve structured provider, organization, model, and variant identity across rescans.
- Add operator-visible root state and failure reporting for invalid roots.

### M12.2 Text And MoE Family Adapters

- Land adapter coverage for the targeted text and MoE families.
- Carry family-specific attention, positional-encoding, and MoE capability metadata into routing.
- Add live integration checks proving those families scan, load, and route correctly.

### M12.3 Image Family Dispatch And Picker Completion

- Add class-based dispatch for the targeted image families.
- Surface family identity and role support in the image picker.
- Add integration checks proving the picker only exposes valid families for the relevant workflow.

### M12.4 Model Inspect, Health, And Conversion Tools

- Add typed inspect-model payloads with stable metadata fields for operators and API consumers.
- Add model health-check output that distinguishes warning, degraded, and failed states.
- Route conversion and quantized packaging through model-ops jobs with stable result metadata.

## M13 Gateway Configuration, Defaults, And API Onboarding

### M13.1 Gateway Config State Model And Persistence

- Add a typed gateway-config model covering network, auth, and serving identity fields.
- Persist operator edits and config-file imports through the supported control-plane path.
- Add tests proving effective settings remain inspectable after precedence resolution.

### M13.2 Generation, Batching, And Speculative Defaults

- Expose default max tokens, temperature, top-p, and stream interval settings.
- Add controls for concurrent processing, max concurrent sequence, prefill batch size, and completion batch size.
- Add speculative-decoding defaults, including draft-model selection and `num-draft-tokens`.

### M13.3 Tooling, Embedding, And Config-File Settings

- Add settings for embedding-model selection and preload.
- Expose built-in tool-parser, MCP, config-file path, and additional-arguments state.
- Add tests proving these settings remain visible and stable after restart and reconnect.

### M13.4 API Reference And Quick-Start Onboarding

- Project the supported API surface into a product-visible reference view.
- Add curl, Python, and JavaScript quick-start snippets for local usage.
- Add smoke execution or verification for the examples so the docs do not drift from shipped behavior.

## M14 Image Iteration And Persisted Creative Workflows

### M14.1 Image Variation And Iterate Request Semantics

- Add request shapes for variations and iterate-from-artifact flows.
- Preserve artifact lineage across base image, source image, variation, and iterate outputs.
- Add protocol and worker coverage for strength-based variations and prompt deltas.

### M14.2 Persisted Image Defaults And Role-Aware Picker

- Persist creative defaults such as steps, size, guidance, strength, and negative prompt.
- Merge persisted defaults with model defaults and per-request overrides deterministically.
- Expose generation-model versus edit-model roles in the picker using capability metadata.

### M14.3 Redo Actions And Long-Running Timeout Policy

- Add always-visible redo and reiteration actions tied to existing artifact lineage.
- Extend image timeout policy to the longer-running creative target and keep timeout state explicit.
- Add tests proving timeout, retry, and cancel behavior stay distinguishable in operator surfaces.

### M14.4 Image Iteration Integration And Artifact-Lineage Evidence

- Add integration coverage for vary, iterate, redo, timeout, and cancel flows.
- Record metrics for variation latency, iterate latency, and timeout-triggered failures.
- Document operator workflows for inspecting lineage and recovering from long-running image jobs.

## M15 Desktop Signals, Download Recovery, And Streaming Polish

### M15.1 Token-Stream Presentation Smoothing

- Add UI-side token smoothing that preserves raw streamed content exactly.
- Track token-render lag so presentation polish can be measured and regressed.
- Add UI tests proving smoothing survives reconnects and terminal stream states.

### M15.2 Update Banners And Runtime Signal Unification

- Add dismissible update-availability banners backed by explicit update state.
- Unify runtime and session banners across dashboard, chat, and status-bar surfaces.
- Add tests proving dismissal policy does not hide critical failure signals.

### M15.3 Download-Queue Persistence And Paused-Recovery

- Persist download-queue state and paused-download metadata across shell restart.
- Restore paused downloads with mirrors, retries, and partial progress intact.
- Expose queue and status-bar messaging that reflects resume, stall, and failure states clearly.

### M15.4 Desktop Polish Integration Evidence

- Add live integration coverage for token smoothing, banner behavior, and download recovery.
- Verify future-facing tabs remain grounded in real product-shell navigation and control-plane state.
- Add operator notes and lightweight metrics for the polished desktop workflows.
