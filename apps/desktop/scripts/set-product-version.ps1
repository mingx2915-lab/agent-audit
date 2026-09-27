[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "project Python is unavailable: .venv\Scripts\python.exe"
}

& $Python (Join-Path $PSScriptRoot "set_product_version.py") --root $RepositoryRoot --version $Version
if ($LASTEXITCODE -ne 0) {
    throw "unable to synchronize AgentAudit product version"
}

$ApiManifest = Join-Path $RepositoryRoot "apps\api\pyproject.toml"
$ApiVersionPattern = '(?m)^version\s*=\s*"' + [regex]::Escape($Version) + '"\s*$'
if (-not [regex]::IsMatch((Get-Content -LiteralPath $ApiManifest -Raw), $ApiVersionPattern)) {
    throw "API product version was not synchronized"
}
