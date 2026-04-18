#!/bin/zsh

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
SCHEMA_DIR="$ROOT_DIR/packages/protocol/schema"
SWIFT_OUT="$ROOT_DIR/packages/protocol/swift"
PYTHON_OUT="$ROOT_DIR/packages/protocol/python"
DESCRIPTOR_OUT="$ROOT_DIR/packages/protocol/descriptors"
UV_CACHE_DIR="$ROOT_DIR/.uv-cache"
SWIFT_HOME="$ROOT_DIR/.swift-home"
CLANG_MODULE_CACHE_PATH="$ROOT_DIR/.build/ModuleCache.noindex"
PROTOCOL_SWIFT_HOME="$SWIFT_HOME/protocol"
PROTOCOL_MODULE_CACHE_PATH="$CLANG_MODULE_CACHE_PATH/protocol"
PYTHON_PROJECT="$ROOT_DIR/services/mlx-worker-python"

PROTO_FILES=(
  "$SCHEMA_DIR/controlplane/v1/control_plane.proto"
  "$SCHEMA_DIR/worker/v1/common.proto"
  "$SCHEMA_DIR/worker/v1/runtime.proto"
  "$SCHEMA_DIR/worker/v1/inference.proto"
  "$SCHEMA_DIR/worker/v1/cache.proto"
  "$SCHEMA_DIR/worker/v1/maintenance.proto"
)

mkdir -p "$SWIFT_OUT" "$PYTHON_OUT" "$DESCRIPTOR_OUT"
mkdir -p "$UV_CACHE_DIR"
mkdir -p "$SWIFT_HOME" "$CLANG_MODULE_CACHE_PATH"
mkdir -p "$PROTOCOL_SWIFT_HOME" "$PROTOCOL_MODULE_CACHE_PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is required" >&2
  exit 1
fi

if ! command -v xcrun >/dev/null 2>&1; then
  echo "error: xcrun is required" >&2
  exit 1
fi

HOME="$PROTOCOL_SWIFT_HOME" CLANG_MODULE_CACHE_PATH="$PROTOCOL_MODULE_CACHE_PATH" xcrun swift build \
  --package-path "$SWIFT_OUT" \
  --product protoc-gen-swift \
  --disable-automatic-resolution >/dev/null

HOME="$PROTOCOL_SWIFT_HOME" CLANG_MODULE_CACHE_PATH="$PROTOCOL_MODULE_CACHE_PATH" xcrun swift build \
  --package-path "$SWIFT_OUT" \
  --product protoc-gen-grpc-swift-2 \
  --disable-automatic-resolution >/dev/null

SWIFT_PLUGIN_BIN_DIR="$(
  HOME="$PROTOCOL_SWIFT_HOME" CLANG_MODULE_CACHE_PATH="$PROTOCOL_MODULE_CACHE_PATH" xcrun swift build \
    --package-path "$SWIFT_OUT" \
    --disable-automatic-resolution \
    --show-bin-path
)"
SWIFT_PLUGIN_BIN="$SWIFT_PLUGIN_BIN_DIR/protoc-gen-swift"
GRPC_SWIFT_PLUGIN_BIN="$SWIFT_PLUGIN_BIN_DIR/protoc-gen-grpc-swift-2"

if [[ ! -x "$SWIFT_PLUGIN_BIN" ]]; then
  echo "error: protoc-gen-swift is unavailable at $SWIFT_PLUGIN_BIN" >&2
  exit 1
fi

if [[ ! -x "$GRPC_SWIFT_PLUGIN_BIN" ]]; then
  echo "error: protoc-gen-grpc-swift-2 is unavailable at $GRPC_SWIFT_PLUGIN_BIN" >&2
  exit 1
fi

UV_CACHE_DIR="$UV_CACHE_DIR" uv run --project "$PYTHON_PROJECT" python -m grpc_tools.protoc \
  --plugin="protoc-gen-swift=$SWIFT_PLUGIN_BIN" \
  --proto_path="$SCHEMA_DIR" \
  --swift_opt=Visibility=Public \
  --swift_out="$SWIFT_OUT" \
  "${PROTO_FILES[@]}"

UV_CACHE_DIR="$UV_CACHE_DIR" uv run --project "$PYTHON_PROJECT" python -m grpc_tools.protoc \
  --plugin="protoc-gen-grpc-swift-2=$GRPC_SWIFT_PLUGIN_BIN" \
  --proto_path="$SCHEMA_DIR" \
  --grpc-swift-2_opt=Visibility=Public \
  --grpc-swift-2_opt=Availability=macOS\ 15.0 \
  --grpc-swift-2_out="$SWIFT_OUT" \
  "$SCHEMA_DIR/worker/v1/runtime.proto" \
  "$SCHEMA_DIR/worker/v1/inference.proto" \
  "$SCHEMA_DIR/worker/v1/cache.proto" \
  "$SCHEMA_DIR/worker/v1/maintenance.proto"

UV_CACHE_DIR="$UV_CACHE_DIR" uv run --project "$PYTHON_PROJECT" python -m grpc_tools.protoc \
  --proto_path="$SCHEMA_DIR" \
  --python_out="$PYTHON_OUT" \
  --grpc_python_out="$PYTHON_OUT" \
  "${PROTO_FILES[@]}"

PYTHON_OUT_PATH="$PYTHON_OUT" python3 - <<'PY'
import os
from pathlib import Path

python_out = Path(os.environ["PYTHON_OUT_PATH"])
replacements = {
    "from worker.v1 import ": "from packages.protocol.python.worker.v1 import ",
    "from controlplane.v1 import ": "from packages.protocol.python.controlplane.v1 import ",
}

for path in python_out.rglob("*.py"):
    text = path.read_text()
    updated = text
    for source, target in replacements.items():
        updated = updated.replace(source, target)
    if updated != text:
        path.write_text(updated)
PY

UV_CACHE_DIR="$UV_CACHE_DIR" uv run --project "$PYTHON_PROJECT" python -m grpc_tools.protoc \
  --proto_path="$SCHEMA_DIR" \
  --include_imports \
  --descriptor_set_out="$DESCRIPTOR_OUT/melix.pb" \
  "${PROTO_FILES[@]}"

find "$PYTHON_OUT" -type d -exec touch "{}/__init__.py" \;
