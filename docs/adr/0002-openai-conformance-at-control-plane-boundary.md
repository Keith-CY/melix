# OpenAI conformance is proved at the control-plane boundary

OpenAI Compatibility Conformance is proved in-process at the Swift control-plane
boundary by a table-driven Conformance Matrix against a recording worker
fixture. A runnable Conformance Harness that opens a real socket is an additive
evidence layer, not the primary proof.

## Context

Issue #1384 asked for an "OpenAI-compatible tool-calling conformance and proxy
parity suite." The phrase "suite" suggests a runnable client that posts HTTP to
a live endpoint. Most compatibility drift, however, lives in deterministic
request translation and response shaping: `max_completion_tokens` mapping,
conflicting token fields, legacy `functions`/`function_call`, `parallel_tool_calls`,
sampling-field passthrough, streaming chunk ordering, and typed error payloads.
Proving those over a live backend would couple the proof to a running model,
thermal state, and network conditions, making conformance flaky and slow.

## Decision

The default conformance proof is the in-process Conformance Matrix: it posts
table-driven OpenAI payloads through `OpenAIHandler`, records the translated
worker request and the response boundary against a recording worker fixture, and
renders a machine-readable report from the same rows. It never opens a socket
and never requires real model weights.

The runnable Conformance Harness — a client that exercises a live local endpoint
or a configured remote Server Profile, with a mock-backend CI mode and a
real-backend smoke mode — is an additive evidence layer filed as a child of
#1384. It reuses the matrix report schema; it does not replace the in-process
matrix as the authoritative compatibility proof.

Proxy Parity (local backend versus a configured remote Server Profile) is a
request/response contract proven on top of this boundary, and is distinct from
remote-provider health and capability probes, which only prove reachability and
advertised features.

## Consequences

Conformance stays deterministic, fast, and runnable in CI without a backend, so
new compatibility fields land with a matrix row rather than a live smoke test.
The trade-off is that the in-process matrix does not exercise real wire framing
or real backend behavior; the Conformance Harness and Proxy Parity children
cover that gap as operator evidence rather than as the gate for every
compatibility change.
