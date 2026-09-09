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

function Test-SpanOverlap([int]$FirstStart, [int]$FirstLength, [int]$SecondStart, [int]$SecondLength) {
    return [Math]::Max($FirstStart, $SecondStart) -lt [Math]::Min(
        $FirstStart + $FirstLength,
        $SecondStart + $SecondLength
    )
}

if ($env:WEZTERM_PANE -notmatch "^[0-9]+$") {
    throw "Installed live acceptance must run inside a WezTerm pane"
}
$paneJson = (& wezterm cli list --format json) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect WezTerm pane topology" }
$panes = @($paneJson | ConvertFrom-Json)
$paneId = [int]$env:WEZTERM_PANE
$target = @($panes | Where-Object { $_.pane_id -eq $paneId })
if ($target.Count -ne 1) { throw "Unable to identify WezTerm pane $paneId" }
$target = $target[0]
$siblings = @(
    $panes | Where-Object { $_.tab_id -eq $target.tab_id -and $_.pane_id -ne $paneId }
)
$hasWidthBoundary = @(
    $siblings | Where-Object {
        $touches =
            $_.left_col + $_.size.cols + 1 -eq $target.left_col -or
            $target.left_col + $target.size.cols + 1 -eq $_.left_col
        $touches -and (Test-SpanOverlap $_.top_row $_.size.rows $target.top_row $target.size.rows)
    }
).Count -gt 0
$hasHeightBoundary = @(
    $siblings | Where-Object {
        $touches =
            $_.top_row + $_.size.rows + 1 -eq $target.top_row -or
            $target.top_row + $target.size.rows + 1 -eq $_.top_row
        $touches -and (Test-SpanOverlap $_.left_col $_.size.cols $target.left_col $target.size.cols)
    }
).Count -gt 0
if (-not $hasWidthBoundary -or -not $hasHeightBoundary) {
    throw "Live resize acceptance requires a disposable pane with both horizontal and vertical split boundaries"
}

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
