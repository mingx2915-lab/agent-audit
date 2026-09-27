#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "${SCRIPT_ROOT}/../../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TARGET_TRIPLE="${TARGET_TRIPLE:-x86_64-unknown-linux-gnu}"
SPEC_PATH="${REPOSITORY_ROOT}/apps/desktop/scripts/agent-audit-sidecar.spec"
OUTPUT_ROOT="${REPOSITORY_ROOT}/apps/desktop/build/sidecar"
DIST_PATH="${OUTPUT_ROOT}/dist"
WORK_PATH="${OUTPUT_ROOT}/work"
TAURI_BINARY_DIRECTORY="${REPOSITORY_ROOT}/apps/desktop/src-tauri/binaries"
TARGET_BINARY="${TAURI_BINARY_DIRECTORY}/agent-audit-sidecar-${TARGET_TRIPLE}"
PYINSTALLER_CONFIG="${PYINSTALLER_CONFIG_DIR:-${REPOSITORY_ROOT}/.tools/pyinstaller}"

mkdir -p "${DIST_PATH}" "${WORK_PATH}" "${TAURI_BINARY_DIRECTORY}" "${PYINSTALLER_CONFIG}"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG}"

"${PYTHON_BIN}" "${SCRIPT_ROOT}/prepare_embedding_model.py"

"${PYTHON_BIN}" -m PyInstaller \
  --noconfirm \
  --distpath "${DIST_PATH}" \
  --workpath "${WORK_PATH}" \
  "${SPEC_PATH}"

BUILT_BINARY="${DIST_PATH}/agent-audit-sidecar"
if [[ ! -f "${BUILT_BINARY}" ]]; then
  echo "PyInstaller did not produce ${BUILT_BINARY}" >&2
  exit 1
fi

cp -- "${BUILT_BINARY}" "${TARGET_BINARY}"
chmod +x "${TARGET_BINARY}"
echo "Built ${TARGET_BINARY}"
