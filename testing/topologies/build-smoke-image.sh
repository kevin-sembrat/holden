#!/usr/bin/env bash
# Builds the holden-smoke-node image used by smoke-test.clab.yaml.
#
# Node containers on this network have no package-mirror access (see
# project-holden-scope.md, Phase 1 status), so tooling can't be installed
# via apt-get at deploy time -- it must be baked into the image at build
# time instead. This script does that by copying the host's already-
# installed busybox-static binary (ip/ping/tc applets) into a minimal
# image built from the already-locally-cached debian:stable-slim base,
# so the whole build runs with zero network access.
set -euo pipefail

if ! command -v busybox &>/dev/null; then
  echo "busybox not found on host -- install it first: sudo apt-get install busybox-static" >&2
  exit 1
fi

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cp "$(command -v busybox)" "$BUILD_DIR/busybox"
cat > "$BUILD_DIR/Dockerfile" <<'EOF'
FROM debian:stable-slim
COPY busybox /usr/local/bin/busybox
RUN chmod +x /usr/local/bin/busybox
EOF

docker build -t holden-smoke-node:latest "$BUILD_DIR"
echo "Built holden-smoke-node:latest"
