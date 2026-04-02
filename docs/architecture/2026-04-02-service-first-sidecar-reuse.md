# Service-First Sidecar Reuse

Date: 2026-04-02

## Summary

Melix remains an `app + cli` product first. Team reuse should default to a same-host
`sidecar service` model rather than extracting the inference hot path into a reusable
in-process library.

This keeps the existing control-plane and worker execution path intact while still giving
other systems a stable service interface for local inference.

## Reuse Layers

Melix now distinguishes three reuse layers explicitly.

### Private Core

The private core stays Melix-internal and is not a supported reuse boundary.

This includes:

- control-plane scheduling and admission
- worker registry truth
- engine cores
- gRPC worker server wiring
- runtime selection and model-family dispatch
- model registry internals beyond the published catalog view

External consumers must not bind to these implementation details directly.

### Stable Service Surface

The stable reuse boundary for external systems is the Melix HTTP service surface.

The expected v1 surface is:

- `POST /v1/chat/completions`
- `POST /v1/completions`
- `POST /v1/responses`
- `POST /v1/embeddings`
- `POST /v1/rerank`
- `GET /v1/models`
- `GET /health`

Authentication and local multi-client access remain part of this layer through the existing
gateway access policy and shared-access configuration.

### Tooling Surface

Benchmark, evaluation, model-ops, and packaging workflows are a separate reuse layer.

They may share repository code with Melix, but they should not run through the default
interactive inference lane by default. The preferred operator shape is a dedicated command
or a dedicated sidecar instance with isolated jobs roots.

## Default Topology

The default reuse topology is same-host sidecars.

Each consuming system should either launch or target its own Melix instance with isolated:

- HTTP port
- runtime directory
- socket paths
- managed model root
- audio runtime-pack root
- model-ops jobs root
- evaluation jobs root
- logs and metrics files

The sidecar instance name is projected through `MELIX_SERVICE_INSTANCE_NAME`.

## Isolation Rules

Service reuse must follow these rules:

- no new in-process SDK abstraction on the inference hot path
- no shared default interactive worker lane for non-interactive workloads by default
- no reuse contract over private worker gRPC APIs
- no coupling external systems to Melix-internal registry or runtime-selection details

The sidecar entrypoints expose the following isolation-oriented environment variables:

- `MELIX_SERVICE_INSTANCE_NAME`
- `MELIX_RUNTIME_DIR`
- `MELIX_MANAGED_MODEL_ROOT`
- `MELIX_AUDIO_RUNTIME_PACK_ROOT`
- `MELIX_MODEL_OPS_JOBS_ROOT`
- `MELIX_EVALUATION_JOBS_ROOT`

These variables exist to isolate service consumers without changing the inference execution
path inside Melix.
