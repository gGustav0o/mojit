[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonPath = (Resolve-Path (Join-Path $projectRoot $Python)).Path
$uv = Join-Path (Split-Path $pythonPath) "uv.exe"
$distRoot = Join-Path $projectRoot "dist\release"
$wheelhouse = Join-Path $distRoot "wheelhouse"
$wheel = Join-Path $distRoot "mojit-1.0.0-py3-none-win_amd64.whl"
$sums = Join-Path $distRoot "SHA256SUMS.txt"

foreach ($line in Get-Content -LiteralPath $sums) {
    if ($line -notmatch "^([0-9a-f]{64})  ([^\\/]+)$") { throw "Malformed SHA256SUMS line: $line" }
    $file = Join-Path $distRoot $Matches[2]
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant()
    if ($actual -ne $Matches[1]) { throw "Checksum mismatch: $($Matches[2])" }
}
& $pythonPath (Join-Path $PSScriptRoot "artifact_contract.py") --wheel $wheel
if ($LASTEXITCODE -ne 0) { throw "Wheel contract failed" }

$pythonInstallRoot = Join-Path $projectRoot "build\release-pythons"
$matrixRoot = Join-Path $projectRoot "build\release-matrix"
$matrixRootFull = [IO.Path]::GetFullPath($matrixRoot)
New-Item -ItemType Directory -Force -Path $pythonInstallRoot | Out-Null
$env:UV_PYTHON_INSTALL_DIR = $pythonInstallRoot
$env:UV_PYTHON_DOWNLOADS = "never"
$env:PYTHONNOUSERSITE = "1"
if (-not $SkipPythonInstall) {
    $env:UV_PYTHON_DOWNLOADS = "automatic"
    & $uv python install --install-dir $pythonInstallRoot --no-bin --no-registry 3.11 3.12 3.13 3.14
    if ($LASTEXITCODE -ne 0) { throw "Managed CPython installation failed" }
    $env:UV_PYTHON_DOWNLOADS = "never"
}

$evidence = @()
foreach ($version in @("3.11", "3.12", "3.13", "3.14")) {
    $interpreter = (& $uv python find --managed-python --no-python-downloads $version).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $interpreter) { throw "CPython $version not available" }
    $cell = Join-Path $matrixRoot ("cp" + $version.Replace(".", ""))
    $cellFull = [IO.Path]::GetFullPath($cell)
    if (-not $cellFull.StartsWith($matrixRootFull + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove unexpected matrix path: $cellFull"
    }
    if (Test-Path -LiteralPath $cell) { Remove-Item -LiteralPath $cell -Recurse -Force }
    & $uv venv --python $interpreter --no-project $cell
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed for $version" }
    $cellPython = Join-Path $cell "Scripts\python.exe"
    & $uv pip install --python $cellPython --offline --no-cache --no-index --find-links $wheelhouse "mojit==1.0.0"
    if ($LASTEXITCODE -ne 0) { throw "offline install failed for $version" }

    $originalPath = $env:Path
    $hostile = Join-Path $matrixRoot "hostile"
    New-Item -ItemType Directory -Force -Path $hostile | Out-Null
    Copy-Item -LiteralPath "$env:SystemRoot\System32\version.dll" -Destination (Join-Path $hostile "libfribidi-0.dll") -Force
    $env:Path = "$hostile;$env:SystemRoot\System32;$env:SystemRoot;$(Join-Path $cell 'Scripts')"
    try {
        $list = (& (Join-Path $cell "Scripts\mojit.exe") --list-effects) -join "`n"
        if ($LASTEXITCODE -ne 0 -or $list -notmatch "neon") { throw "installed console smoke failed for $version" }
        & $cellPython -m mojit --help | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "installed module smoke failed for $version" }
        $probeJson = (& $cellPython (Join-Path $PSScriptRoot "installed_probe.py")) -join ""
        if ($LASTEXITCODE -ne 0) { throw "native/typography probe failed for $version" }
        $probe = $probeJson | ConvertFrom-Json
        if (-not $probe.raqm -or $probe.fribidi_sha256 -ne "4283ba30461395fdf46399b2665176e6f41d11bc7bf6977188120152fde31fd2") {
            throw "invalid native evidence for $version"
        }
        $missingFont = Join-Path $cell "missing-font.ttc"
        $sampleText = -join @([char]0x96FB, [char]0x8133, [char]0x4E16, [char]0x754C)
        & (Join-Path $cell "Scripts\mojit.exe") $sampleText --font $missingFont 2>$null | Out-Null
        if ($LASTEXITCODE -ne 2) { throw "missing-font failure contract failed for $version" }

        $installedDll = $probe.fribidi
        $heldDll = "$installedDll.phase6-missing"
        Move-Item -LiteralPath $installedDll -Destination $heldDll
        try {
            & $cellPython -m mojit --help 2>$null | Out-Null
            if ($LASTEXITCODE -ne 2) { throw "missing-native failure contract failed for $version" }
        } finally {
            Move-Item -LiteralPath $heldDll -Destination $installedDll
        }
        $evidence += $probe
    } finally {
        $env:Path = $originalPath
    }

    & $uv pip uninstall --python $cellPython mojit
    if ($LASTEXITCODE -ne 0) { throw "uninstall failed for $version" }
    if (Test-Path -LiteralPath $probe.fribidi) { throw "uninstall left native payload for $version" }
    & $uv pip install --python $cellPython --offline --no-cache --no-index --find-links $wheelhouse "mojit==1.0.0"
    if ($LASTEXITCODE -ne 0) { throw "offline reinstall failed for $version" }
}

$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $distRoot "PYTHON_MATRIX.json") -Encoding utf8
Write-Host "Artifact verification and CPython 3.11-3.14 matrix passed"
