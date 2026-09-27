"""Build the fixed-lifecycle API Sidecar used by the Tauri desktop bundle."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


REPOSITORY_ROOT = Path(SPEC).resolve().parents[3]
API_SOURCE = REPOSITORY_ROOT / "apps" / "api" / "src"
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"
EMBEDDING_MODEL = REPOSITORY_ROOT / ".tools" / "embedding-model"
ENTRYPOINT = Path(SPEC).resolve().parent / "sidecar_entry.py"


hiddenimports = collect_submodules("agent_audit_api") + collect_submodules("fastembed")
if not (EMBEDDING_MODEL / "model_optimized.onnx").is_file():
    raise RuntimeError("Run prepare_embedding_model.py before building the Sidecar")
datas = [
    (str(DEMO_SEED), "demo-seed"),
    (str(EMBEDDING_MODEL), "embedding-model"),
    *collect_data_files("fastembed"),
    *copy_metadata("agent-audit-api", recursive=True),
]

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(API_SOURCE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="agent-audit-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
