[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonPath = (Resolve-Path (Join-Path $projectRoot $Python)).Path
$releaseVersion = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION") -Raw -Encoding ascii).Trim()
if ($releaseVersion -notmatch "^[0-9]+\.[0-9]+\.[0-9]+$") {
    throw "Invalid release VERSION: $releaseVersion"
}
$uv = Join-Path (Split-Path $pythonPath) "uv.exe"
$distRoot = Join-Path $projectRoot "dist\release"
$wheelhouse = Join-Path $distRoot "wheelhouse"
$wheel = Join-Path $distRoot "mojit-$releaseVersion-py3-none-win_amd64.whl"
$bundle = Join-Path $distRoot "mojit-$releaseVersion-windows-x64-wheelhouse.zip"
$sums = Join-Path $distRoot "SHA256SUMS.txt"

foreach ($line in Get-Content -LiteralPath $sums) {
    if ($line -notmatch "^([0-9a-f]{64})  ([^\\/]+)$") { throw "Malformed SHA256SUMS line: $line" }
    $file = Join-Path $distRoot $Matches[2]
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant()
    if ($actual -ne $Matches[1]) { throw "Checksum mismatch: $($Matches[2])" }
}
& $pythonPath (Join-Path $PSScriptRoot "artifact_contract.py") --wheel $wheel
if ($LASTEXITCODE -ne 0) { throw "Wheel contract failed" }
& $pythonPath (Join-Path $PSScriptRoot "artifact_contract.py") --bundle $bundle
if ($LASTEXITCODE -ne 0) { throw "Wheelhouse bundle contract failed" }

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
foreach ($pythonVersion in @("3.11", "3.12", "3.13", "3.14")) {
    $interpreter = (& $uv python find --managed-python --no-python-downloads $pythonVersion).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $interpreter) {
        throw "CPython $pythonVersion not available"
    }
    $cell = Join-Path $matrixRoot ("cp" + $pythonVersion.Replace(".", ""))
    $cellFull = [IO.Path]::GetFullPath($cell)
    if (-not $cellFull.StartsWith($matrixRootFull + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove unexpected matrix path: $cellFull"
    }
    if (Test-Path -LiteralPath $cell) { Remove-Item -LiteralPath $cell -Recurse -Force }
    & $uv venv --python $interpreter --no-project $cell
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed for $pythonVersion" }
    $cellPython = Join-Path $cell "Scripts\python.exe"
    & $uv pip install --python $cellPython --offline --no-cache --no-index --find-links $wheelhouse "mojit==$releaseVersion"
    if ($LASTEXITCODE -ne 0) { throw "offline install failed for $pythonVersion" }

    $originalPath = $env:Path
    $hostile = Join-Path $matrixRoot "hostile"
    New-Item -ItemType Directory -Force -Path $hostile | Out-Null
    Copy-Item -LiteralPath "$env:SystemRoot\System32\version.dll" -Destination (Join-Path $hostile "libfribidi-0.dll") -Force
    $env:Path = "$hostile;$env:SystemRoot\System32;$env:SystemRoot;$(Join-Path $cell 'Scripts')"
    try {
        $list = (& (Join-Path $cell "Scripts\mojit.exe") --list-effects) -join "`n"
        if ($LASTEXITCODE -ne 0 -or $list -ne "chromatic`nglitch`nneon`npulse") {
            throw "installed effect listing smoke failed for $pythonVersion"
        }
        $sceneList = (& (Join-Path $cell "Scripts\mojit.exe") --list-scenes) -join "`n"
        if ($LASTEXITCODE -ne 0 -or $sceneList -ne "rainy-night`nsnowfall`nspace") {
            throw "installed scene listing smoke failed for $pythonVersion"
        }
        $installedHelp = (& (Join-Path $cell "Scripts\mojit.exe") -h) -join "`n"
        if (
            $LASTEXITCODE -ne 0 -or
            $installedHelp -notmatch "--margin RATIO" -or
            $installedHelp -notmatch "Configuration precedence"
        ) {
            throw "installed help contract failed for $pythonVersion"
        }
        $probeJson = (& $cellPython (Join-Path $PSScriptRoot "installed_probe.py")) -join ""
        if ($LASTEXITCODE -ne 0) { throw "native/typography probe failed for $pythonVersion" }
        $probe = $probeJson | ConvertFrom-Json
        if (
            -not $probe.raqm -or
            $probe.mojit_version -ne $releaseVersion -or
            $probe.fribidi_sha256 -ne "4283ba30461395fdf46399b2665176e6f41d11bc7bf6977188120152fde31fd2" -or
            -not $probe.scene_render_deterministic -or
            ($probe.scenes -join ",") -ne "rainy-night,snowfall,space" -or
            ($probe.built_in_scenes_rendered -join ",") -ne "rainy-night,snowfall,space" -or
            ($probe.scene_config_layers -join ",") -ne "stars,rain,text"
        ) {
            throw "invalid native evidence for $pythonVersion"
        }
        $missingFont = Join-Path $cell "missing-font.ttc"
        $sampleText = -join @([char]0x96FB, [char]0x8133, [char]0x4E16, [char]0x754C)
        & (Join-Path $cell "Scripts\mojit.exe") $sampleText --font $missingFont 2>$null | Out-Null
        if ($LASTEXITCODE -ne 2) {
            throw "missing-font failure contract failed for $pythonVersion"
        }

        $installedDll = $probe.fribidi
        $heldDll = "$installedDll.phase6-missing"
        Move-Item -LiteralPath $installedDll -Destination $heldDll
        try {
            & $cellPython -m mojit --help 2>$null | Out-Null
            if ($LASTEXITCODE -ne 2) {
                throw "missing-native failure contract failed for $pythonVersion"
            }
        } finally {
            Move-Item -LiteralPath $heldDll -Destination $installedDll
        }
        $evidence += $probe
    } finally {
        $env:Path = $originalPath
    }

    & $uv pip uninstall --python $cellPython mojit
    if ($LASTEXITCODE -ne 0) { throw "uninstall failed for $pythonVersion" }
    if (Test-Path -LiteralPath $probe.fribidi) {
        throw "uninstall left native payload for $pythonVersion"
    }
    & $uv pip install --python $cellPython --offline --no-cache --no-index --find-links $wheelhouse "mojit==$releaseVersion"
    if ($LASTEXITCODE -ne 0) { throw "offline reinstall failed for $pythonVersion" }
}

$evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $distRoot "PYTHON_MATRIX.json") -Encoding utf8

$installer = Join-Path $wheelhouse "install.ps1"
$installerRoot = Join-Path $projectRoot "build\release-installer"
$installerRootFull = [IO.Path]::GetFullPath($installerRoot)
$buildRootFull = [IO.Path]::GetFullPath((Join-Path $projectRoot "build"))
if (-not $installerRootFull.StartsWith($buildRootFull + [IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to use unexpected installer verification path: $installerRootFull"
}
if (Test-Path -LiteralPath $installerRoot) {
    $oldMarker = Join-Path $installerRoot ".mojit-install.json"
    if (-not (Test-Path -LiteralPath $oldMarker -PathType Leaf)) {
        throw "Refusing to remove unowned installer verification path: $installerRoot"
    }
    & $installer -Uninstall -InstallRoot $installerRoot -PathScope None
    if ($LASTEXITCODE -ne 0) { throw "Prior installer verification cleanup failed" }
}
$installerPython = (& $uv python find --managed-python --no-python-downloads 3.13).Trim()
if ($LASTEXITCODE -ne 0 -or -not $installerPython) {
    throw "CPython 3.13 is unavailable for installer verification"
}
Push-Location $matrixRoot
try {
    & $installer -Python $installerPython -Wheelhouse $wheelhouse -InstallRoot $installerRoot -PathScope Process
    if ($LASTEXITCODE -ne 0) { throw "User installer verification failed" }
    & $installer -Wheelhouse $wheelhouse -InstallRoot $installerRoot -PathScope Process
    if ($LASTEXITCODE -ne 0) { throw "User installer upgrade verification failed" }
    $installedCommand = Join-Path $installerRoot "Scripts\mojit.exe"
    $installedEffects = (& $installedCommand --list-effects) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $installedEffects -ne "chromatic`nglitch`nneon`npulse") {
        throw "Installed global command smoke failed outside its installation directory"
    }
    $installedScenes = (& $installedCommand --list-scenes) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $installedScenes -ne "rainy-night`nsnowfall`nspace") {
        throw "Installed global scene smoke failed outside its installation directory"
    }
    & (Join-Path $installerRoot "install.ps1") -Uninstall -PathScope None
    if ($LASTEXITCODE -ne 0 -or (Test-Path -LiteralPath $installerRoot)) {
        throw "User uninstaller verification failed"
    }
} finally {
    Pop-Location
}
Write-Host "Artifact, CPython 3.11-3.14, and user installer verification passed"
