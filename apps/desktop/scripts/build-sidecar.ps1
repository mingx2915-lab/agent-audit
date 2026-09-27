param(
    [string]$Python = "",
    [string]$TargetTriple = "x86_64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$ProjectPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = if (Test-Path -LiteralPath $ProjectPython -PathType Leaf) {
        $ProjectPython
    } else {
        "python"
    }
}
$SpecPath = Join-Path $RepositoryRoot "apps\desktop\scripts\agent-audit-sidecar.spec"
$OutputRoot = Join-Path $RepositoryRoot "apps\desktop\build\sidecar"
$DistPath = Join-Path $OutputRoot "dist"
$WorkPath = Join-Path $OutputRoot "work"
$TauriBinaryDirectory = Join-Path $RepositoryRoot "apps\desktop\src-tauri\binaries"
$TargetBinary = Join-Path $TauriBinaryDirectory "agent-audit-sidecar-$TargetTriple.exe"
$PyInstallerConfig = Join-Path $RepositoryRoot ".tools\pyinstaller"

New-Item -ItemType Directory -Force -Path $DistPath, $WorkPath, $TauriBinaryDirectory, $PyInstallerConfig | Out-Null
$env:PYINSTALLER_CONFIG_DIR = $PyInstallerConfig

& $Python (Join-Path $PSScriptRoot "prepare_embedding_model.py")
if ($LASTEXITCODE -ne 0) { throw "Embedding model preparation failed" }

& $Python -m PyInstaller `
  --noconfirm `
  --distpath $DistPath `
  --workpath $WorkPath `
  $SpecPath

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$BuiltBinary = Join-Path $DistPath "agent-audit-sidecar.exe"
if (-not (Test-Path -LiteralPath $BuiltBinary -PathType Leaf)) {
    throw "PyInstaller did not produce $BuiltBinary"
}

Copy-Item -LiteralPath $BuiltBinary -Destination $TargetBinary -Force
Write-Output "Built $TargetBinary"
