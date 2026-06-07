# Service-First Reuse

## Purpose

Use this runbook when another local system needs Melix capabilities without embedding Melix
internals as a library.

The recommended model is a same-host sidecar instance per consumer or per workload class.

## Stable Service Surface

Treat these endpoints as the supported local reuse boundary:

- `POST /v1/chat/completions`
- `POST /v1/completions`
- `POST /v1/responses`
- `POST /v1/embeddings`
- `POST /v1/rerank`
- `GET /v1/models`
- `GET /health`
- `GET /v1/melix/health`

`GET /health` is a public liveness probe. Use authenticated `GET /v1/melix/health`
when a consumer needs route readiness or model-count diagnostics.

Use shared-access configuration only when more than one client needs to reach the same
sidecar instance.

The local gateway applies the Host and browser Origin policy described in
`docs/runbooks/shared-access.md` before route handling. Same-host server clients
that omit `Origin` continue to work with the active auth policy; browser clients
must use explicit `MELIX_ALLOWED_ORIGINS` configuration.

## Sidecar Install

Create a named local product layout for one consumer:

```bash
python3 scripts/install_local_product.py \
  --service-instance-name team-a \
  --http-port 12434 \
  --json
```

This writes instance-specific assets under:

- `~/.melix/sidecars/team-a`
- `~/.melix/sidecars/team-a/logs`
- `~/Library/LaunchAgents/io.melix.team-a.*.plist`

The generated environment script exports isolated roots for runtime, models, runtime packs,
and tooling jobs.

## Ephemeral Development Sidecar

For repository-local development or smoke work, start a named sidecar with isolated runtime
state:

```bash
MELIX_SERVICE_INSTANCE_NAME=team-a \
MELIX_HTTP_PORT=12434 \
bash scripts/dev_up.sh
```

This defaults the runtime directory to:

```text
.runtime/sidecars/team-a
```

and exports instance-specific paths for:

- managed models
- audio runtime packs
- model-ops jobs
- evaluation jobs

## Tooling Isolation

Do not run benchmark or evaluation traffic through the default interactive sidecar instance
unless the interference is intentional.

Preferred patterns:

1. Launch a separate sidecar instance for tooling traffic.
2. Point tooling workloads at separate jobs roots via the exported sidecar environment.

Example:

```bash
MELIX_SERVICE_INSTANCE_NAME=team-a-bench \
MELIX_HTTP_PORT=12435 \
bash scripts/dev_up.sh
```

Use the dedicated tooling instance for:

- benchmark collection
- evaluation runs
- model conversion or quantization
- training or adapter workflows

## Verification

After startup, verify the sidecar directly:

```bash
curl -sS http://127.0.0.1:${MELIX_HTTP_PORT}/health
curl -sS http://127.0.0.1:${MELIX_HTTP_PORT}/v1/melix/health
curl -sS http://127.0.0.1:${MELIX_HTTP_PORT}/v1/models
```

When the same host runs more than one sidecar, confirm:

- HTTP ports differ
- runtime directories differ
- socket paths differ
- managed model and tooling roots differ

## Recovery

If a sidecar collides with an existing local stack:

1. Choose a different `MELIX_SERVICE_INSTANCE_NAME`.
2. Choose a different `MELIX_HTTP_PORT`.
3. Confirm the generated runtime and model roots differ from the existing instance.
4. Restart the affected sidecar only.
