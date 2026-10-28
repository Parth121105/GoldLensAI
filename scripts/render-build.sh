#!/usr/bin/env bash
# Render build for the single GoldLensAI web service (see render.yaml).
# Builds the React frontend into frontend/dist, then installs the pinned
# backend dependencies. FastAPI serves frontend/dist at runtime.
set -euo pipefail

cd "$(dirname "$0")/.."

node_version="$(node --version)"
if [[ "$node_version" != v24.* ]]; then
  echo "error: Node 24 is required for the frontend build, found $node_version" >&2
  exit 1
fi
echo "Using $(python --version 2>&1), Node $node_version, npm $(npm --version)"

# --include=dev: the build needs TypeScript and Vite even if NODE_ENV=production.
(cd frontend && npm ci --include=dev && npm run build)
test -f frontend/dist/index.html

pip install -r backend/requirements.txt

# The synthetic validation takes minutes on the free instance's CPU; compute it once here.
(cd backend && python -m app.cli precompute-synthetic)
