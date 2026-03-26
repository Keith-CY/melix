# Melix

Melix is a local-first AI runtime for Apple Silicon. The first implementation slice in this repository focuses on:

- generated protocol artifacts from the shared protobuf schema
- a Swift control plane workspace
- a Python worker workspace
- a minimal macOS menu bar workspace

Repository-wide engineering guidance lives in:

- `AGENTS.md`
- `docs/README.md`
- `docs/engineering-standards.md`
- `docs/plans/2026-03-27-phase-0-thin-path.md`

## Prerequisites

- macOS on Apple Silicon
- `swift`
- `python3`
- `uv`
- `protoc`
- `protoc-gen-swift` for Swift protobuf generation

## First Slice Developer Flow

```bash
make bootstrap
make proto
make swift-test
make py-test
make integration-test
make coverage
```

`make proto` currently generates:

- Swift protobuf message types into `packages/protocol/swift`
- Python protobuf and gRPC artifacts into `packages/protocol/python`

## Repository Policies

- `packages/protocol/schema` is the authoritative interface source.
- Generated protobuf outputs are committed artifacts and must be regenerated after schema changes.
- `uv.lock` is committed and Python environments should be reproduced with `uv sync --frozen`.
- Executable Swift workspaces should commit `Package.resolved` when it exists.
- `docs/product-brief.md` is intentionally ignored and untracked.
- `make coverage` is the repository entrypoint for source coverage checks before commit.

The live runtime, HTTP gateway, and menu bar behavior are added incrementally in later tasks under `docs/plans/2026-03-27-phase-0-thin-path.md`.
