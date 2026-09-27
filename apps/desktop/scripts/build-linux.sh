#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "${SCRIPT_ROOT}/../../.." && pwd)"
TARGET_TRIPLE="${TARGET_TRIPLE:-x86_64-unknown-linux-gnu}"
export TARGET_TRIPLE

"${REPOSITORY_ROOT}/apps/desktop/scripts/build-sidecar.sh"
npm run build --workspace @agent-audit/contracts
npm run build --workspace @agent-audit/web
npm run build --workspace @agent-audit/desktop -- --target "${TARGET_TRIPLE}"
