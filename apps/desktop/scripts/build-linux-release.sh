#!/usr/bin/env bash
# Evidence runner executes AppImage with --appimage-extract-and-run, verifies
# loopback 127.0.0.1 health, and writes SHA-256 checksums.
set -euo pipefail

SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "${SCRIPT_ROOT}/../../.." && pwd)"
OUTPUT_DIR="${1:?usage: build-linux-release.sh OUTPUT_DIR PROBE_EXECUTABLE}"
PROBE_EXECUTABLE="${2:?usage: build-linux-release.sh OUTPUT_DIR PROBE_EXECUTABLE}"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "Linux x86_64 runner is required" >&2
  exit 2
fi
if [[ -e "${OUTPUT_DIR}" && -n "$(find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "output directory must be empty" >&2
  exit 2
fi
if [[ ! -f "${PROBE_EXECUTABLE}" || -L "${PROBE_EXECUTABLE}" || ! -x "${PROBE_EXECUTABLE}" ]]; then
  echo "secret service probe must be an explicit executable regular file" >&2
  exit 2
fi
PROBE_EXECUTABLE="$(cd -- "$(dirname -- "${PROBE_EXECUTABLE}")" && pwd)/$(basename -- "${PROBE_EXECUTABLE}")"
PROBE_RESULT="$(${PROBE_EXECUTABLE})"
if [[ "${PROBE_RESULT}" != "secret_service_probe=passed" ]]; then
  echo "secret service probe did not produce the expected result" >&2
  exit 1
fi

VERSION="$(python3 - <<'PY'
import json, re
from pathlib import Path
root = Path('.')
versions = [
    json.loads((root / 'package.json').read_text(encoding='utf-8'))['version'],
    json.loads((root / 'apps/desktop/package.json').read_text(encoding='utf-8'))['version'],
    json.loads((root / 'apps/desktop/src-tauri/tauri.conf.json').read_text(encoding='utf-8'))['version'],
]
for relative, pattern in (
    ('apps/desktop/src-tauri/Cargo.toml', r'(?ms)^\[package\].*?^version\s*=\s*"([^"]+)"'),
    ('apps/desktop/src-tauri/Cargo.lock', r'(?ms)^\[\[package\]\]\s*name\s*=\s*"agent-audit-desktop"\s*version\s*=\s*"([^"]+)"'),
    ('apps/api/pyproject.toml', r'(?ms)^\[project\].*?^version\s*=\s*"([^"]+)"'),
):
    match = re.search(pattern, (root / relative).read_text(encoding='utf-8'))
    if match is None:
        raise SystemExit(f'missing version in {relative}')
    versions.append(match.group(1))
if len(set(versions)) != 1:
    raise SystemExit('product versions are inconsistent')
print(versions[0])
PY
)"

STAGING="$(mktemp -d)"
trap 'rm -rf -- "${STAGING}"' EXIT
export TARGET_TRIPLE="x86_64-unknown-linux-gnu"
export CARGO_TARGET_DIR="${STAGING}/cargo-target"
export PYINSTALLER_CONFIG_DIR="${STAGING}/pyinstaller"
export AGENT_AUDIT_HOME="${STAGING}/agent-audit-home"
unset AGENT_AUDIT_PROVIDER_API_KEY PROVIDER_API_KEY OPENAI_API_KEY DEEPSEEK_API_KEY ANTHROPIC_API_KEY OLLAMA_HOST || true

cd -- "${REPOSITORY_ROOT}"
bash apps/desktop/scripts/build-sidecar.sh
npm run typecheck
npm run build
TAURI_LINUX_CONFIG="${REPOSITORY_ROOT}/apps/desktop/src-tauri/tauri.linux.conf.json"
npm run build --workspace @agent-audit/desktop -- \
  --target "${TARGET_TRIPLE}" --config "${TAURI_LINUX_CONFIG}"

mkdir -p -- "${OUTPUT_DIR}"
cp -- "apps/desktop/src-tauri/binaries/agent-audit-sidecar-${TARGET_TRIPLE}" "${OUTPUT_DIR}/agent-audit-sidecar"
find "${CARGO_TARGET_DIR}/${TARGET_TRIPLE}/release/bundle" -type f \( -name '*.deb' -o -name '*.AppImage' \) -exec cp -- '{}' "${OUTPUT_DIR}/" \;
[[ "$(find "${OUTPUT_DIR}" -maxdepth 1 -name '*.deb' | wc -l)" -eq 1 ]]
[[ "$(find "${OUTPUT_DIR}" -maxdepth 1 -name '*.AppImage' | wc -l)" -eq 1 ]]
mapfile -t DEB_FILES < <(find "${OUTPUT_DIR}" -maxdepth 1 -type f -name '*.deb')
mapfile -t APPIMAGE_FILES < <(find "${OUTPUT_DIR}" -maxdepth 1 -type f -name '*.AppImage')
[[ "${#DEB_FILES[@]}" -eq 1 && "${#APPIMAGE_FILES[@]}" -eq 1 ]]
file "${OUTPUT_DIR}/agent-audit-sidecar" "${DEB_FILES[0]}" "${APPIMAGE_FILES[0]}"

# Exercise the packaged WebView and the real GTK file chooser before the
# artifact summary is generated.  WebView elements are located through the
# official Tauri WebDriver stack; xdotool is scoped to the titled native
# chooser only.  Missing tooling or a failed selection must stop this release
# instead of leaving a falsely complete evidence summary.
DEB_PICKER_ROOT="${STAGING}/deb-picker-root"
dpkg-deb -x "${DEB_FILES[0]}" "${DEB_PICKER_ROOT}"
PICKER_EVIDENCE="${STAGING}/native-picker-evidence.json"
xvfb-run -a bash -c '
  set -euo pipefail
  wm_log="$(mktemp)"
  openbox --sm-disable >"${wm_log}" 2>&1 &
  wm_pid=$!
  cleanup_wm() {
    kill -TERM "${wm_pid}" 2>/dev/null || true
    wait "${wm_pid}" 2>/dev/null || true
    rm -f -- "${wm_log}"
  }
  trap cleanup_wm EXIT
  python3 "$@"
' bash apps/desktop/scripts/linux_native_picker_evidence.py \
  --appimage "${APPIMAGE_FILES[0]}" \
  --deb "${DEB_FILES[0]}" \
  --deb-desktop "${DEB_PICKER_ROOT}/usr/bin/agent-audit-desktop" \
  --output "${PICKER_EVIDENCE}"

python3 apps/desktop/scripts/linux_artifact_evidence.py \
  --appimage "${APPIMAGE_FILES[0]}" \
  --deb "${DEB_FILES[0]}" \
  --sidecar "${OUTPUT_DIR}/agent-audit-sidecar" \
  --version "${VERSION}" \
  --output-dir "${OUTPUT_DIR}/evidence" \
  --picker-evidence "${PICKER_EVIDENCE}" \
  --secret-service-verified
