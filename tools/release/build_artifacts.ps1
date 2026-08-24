[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonPath = (Resolve-Path (Join-Path $projectRoot $Python)).Path
$distRoot = Join-Path $projectRoot "dist\release"
$wheelhouse = Join-Path $distRoot "wheelhouse"
if (Test-Path -LiteralPath $distRoot) {
    $resolvedDist = (Resolve-Path -LiteralPath (Join-Path $projectRoot "dist")).Path
    $resolvedRelease = (Resolve-Path -LiteralPath $distRoot).Path
    if (-not $resolvedRelease.StartsWith($resolvedDist + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove unexpected release path: $resolvedRelease"
    }
    Remove-Item -LiteralPath $resolvedRelease -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $wheelhouse | Out-Null

$env:SOURCE_DATE_EPOCH = "1787443200"
& $pythonPath -m build --wheel --no-isolation --outdir $distRoot
if ($LASTEXITCODE -ne 0) { throw "Wheel build failed" }
$wheel = Get-Item (Join-Path $distRoot "mojit-1.0.0-py3-none-win_amd64.whl")
& $pythonPath (Join-Path $PSScriptRoot "artifact_contract.py") --wheel $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw "Wheel contract failed" }
Copy-Item -LiteralPath $wheel.FullName -Destination $wheelhouse

& $pythonPath -m pip download --disable-pip-version-check --only-binary=:all: --no-deps --dest $wheelhouse "budoux==0.9.0"
if ($LASTEXITCODE -ne 0) { throw "BudouX dependency download failed" }

foreach ($minor in @("311", "312", "313", "314")) {
    & $pythonPath -m pip download --disable-pip-version-check --only-binary=:all: --no-deps --dest $wheelhouse --platform win_amd64 --implementation cp --python-version $minor --abi "cp$minor" "numpy==2.4.6" "Pillow==12.3.0"
    if ($LASTEXITCODE -ne 0) { throw "Dependency download failed for CPython $minor" }
}

$bundle = Join-Path $distRoot "mojit-1.0.0-windows-x64-wheelhouse.zip"
& $pythonPath (Join-Path $PSScriptRoot "artifact_contract.py") --zip-source $wheelhouse --zip-target $bundle
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") -Destination $distRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "vendor\fribidi\source\fribidi-1.0.16.tar.xz") -Destination $distRoot

$files = Get-ChildItem -LiteralPath $distRoot -File | Sort-Object Name
$lines = foreach ($file in $files) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    "$hash  $($file.Name)"
}
Set-Content -LiteralPath (Join-Path $distRoot "SHA256SUMS.txt") -Value $lines -Encoding ascii
Write-Host "Release candidate created at $distRoot"
