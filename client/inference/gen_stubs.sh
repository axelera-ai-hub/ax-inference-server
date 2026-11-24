#!/bin/bash
#
# Generate the Python gRPC stubs for the axinfer.v1 inference service.
#
# Removes and recreates inference/generated, then runs protoc on
# proto/axinfer/v1/inference.proto at the repository root.
#
# USAGE:
#   ./gen_stubs.sh
#
# DEPENDENCIES:
#   - python3 (runs grpc_tools.protoc)
#   - grpcio-tools (installed with pip if the import fails)
#
# EXIT CODES:
#   0: Success.
#   1: The stubs were not generated.
#   other: A failing command under set -e.
#
# EXAMPLE:
#   ./gen_stubs.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFERENCE_SERVER_ROOT="$(cd "$HERE/../.." && pwd)"
OUT_DIR="$HERE/generated"

python3 -c "import grpc_tools" 2>/dev/null || pip install grpcio-tools

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
python3 -m grpc_tools.protoc --proto_path="$INFERENCE_SERVER_ROOT/proto" \
  --python_out="$OUT_DIR" --grpc_python_out="$OUT_DIR" \
  "$INFERENCE_SERVER_ROOT/proto/axinfer/v1/inference.proto"

test -f "$OUT_DIR/axinfer/v1/inference_pb2_grpc.py" || { echo "ERROR: stubs not generated" >&2; exit 1; }
echo "gen_stubs.sh: PASS ($OUT_DIR)"
