[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Python,
    [string]$ProjectRoot = "",
    [double]$SoakSeconds = 300,
    [string]$ResultFile = ""
)

$ErrorActionPreference = "Stop"
if (-not $ProjectRoot) { $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
if (-not $ResultFile) { $ResultFile = Join-Path $ProjectRoot "build\installed-live.exit" }
$env:MOJIT_LIVE_SOAK_SECONDS = $SoakSeconds.ToString([Globalization.CultureInfo]::InvariantCulture)
$env:PYTHONNOUSERSITE = "1"
$exitCode = 1
try {
    & $Python -m pytest (Join-Path $ProjectRoot "tests\live\wezterm_acceptance.py") -m wezterm_live -q -s -p no:cacheprovider
    $exitCode = $LASTEXITCODE
} finally {
    Set-Content -LiteralPath $ResultFile -Value $exitCode -Encoding ascii
}
Write-Host "MOJIT_INSTALLED_LIVE_EXIT=$exitCode"
Read-Host "Acceptance complete; pane may be closed"
exit $exitCode
