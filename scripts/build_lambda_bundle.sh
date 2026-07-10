#!/usr/bin/env bash
# Build a Linux x86_64 Lambda deployment bundle (no Docker required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE="$ROOT/lambda_bundle"

rm -rf "$BUNDLE"
mkdir -p "$BUNDLE"

pip install \
  --platform manylinux2014_x86_64 \
  --python-version 3.11 \
  --implementation cp \
  --only-binary=:all: \
  --target "$BUNDLE" \
  "$ROOT[api]"

cp -r "$ROOT/scripts" "$BUNDLE/scripts"
if [[ -d "$ROOT/static" ]]; then
  cp -r "$ROOT/static" "$BUNDLE/static"
fi

echo "Lambda bundle ready at $BUNDLE ($(du -sh "$BUNDLE" | cut -f1))"
