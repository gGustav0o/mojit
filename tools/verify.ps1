[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $projectRoot "build"
$candidate = Join-Path $projectRoot $Python
if (Test-Path -LiteralPath $candidate -PathType Leaf) {
    $pythonPath = (Resolve-Path -LiteralPath $candidate).Path
} else {
    $command = @(Get-Command $Python -CommandType Application -ErrorAction Stop)[0]
    $pythonPath = $command.Source
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)]
        [string]$Label,
        [Parameter(Mandatory)]
        [scriptblock]$Command
    )
    Write-Host "==> $Label"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

$verificationRoot = Join-Path $buildRoot ("source-verification-" + [guid]::NewGuid().ToString("N"))
$verificationRootFull = [IO.Path]::GetFullPath($verificationRoot)
$buildRootFull = [IO.Path]::GetFullPath($buildRoot)
if (-not $verificationRootFull.StartsWith($buildRootFull + [IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to use verification path outside build: $verificationRootFull"
}
New-Item -ItemType Directory -Force -Path $verificationRoot | Out-Null

try {
    Push-Location $projectRoot
    try {
        Invoke-Checked "environment validation" {
            & $pythonPath -c "import build, numpy, PIL, pytest, ruff; print('verification imports: ok')"
        }
        if (Get-Command git -ErrorAction SilentlyContinue) {
            $trackedGenerated = @(
                & git ls-files -- "build/**" "dist/**" "*.rar" "*.zip" "*.7z" "*.whl"
            )
            if ($LASTEXITCODE -ne 0) { throw "Tracked generated-file inventory failed" }
            $presentTrackedGenerated = @(
                $trackedGenerated | Where-Object { Test-Path -LiteralPath (Join-Path $projectRoot $_) }
            )
            if ($presentTrackedGenerated.Count -ne 0) {
                throw "Build outputs and release archives must not be tracked: $($presentTrackedGenerated -join ', ')"
            }
        }
        Invoke-Checked "lint" { & $pythonPath -m ruff check src tests tools }
        Invoke-Checked "format" { & $pythonPath -m ruff format --check src tests tools }
        Invoke-Checked "tests and coverage" {
            & $pythonPath -m pytest -q -m "not wezterm_live" --cov=mojit --cov-report=term-missing --cov-fail-under=95
        }
        Invoke-Checked "bytecode compilation" { & $pythonPath -m compileall -q src tests tools }
        Invoke-Checked "source CLI effect listing" { & $pythonPath -m mojit --list-effects }
        Invoke-Checked "source CLI scene listing" { & $pythonPath -m mojit --list-scenes }
        Invoke-Checked "wheel build" {
            & $pythonPath -m build --wheel --no-isolation --outdir (Join-Path $verificationRoot "wheel")
        }

        $wheel = Get-ChildItem -LiteralPath (Join-Path $verificationRoot "wheel") -Filter "*.whl"
        if ($wheel.Count -ne 1) { throw "Expected exactly one built wheel, got $($wheel.Count)" }
        $installRoot = Join-Path $verificationRoot "installed"
        Invoke-Checked "isolated installed-artifact environment" {
            & $pythonPath -m venv --system-site-packages $installRoot
        }
        $installedPython = Join-Path $installRoot "Scripts\python.exe"
        Invoke-Checked "isolated wheel installation" {
            & $installedPython -m pip install --disable-pip-version-check --no-deps --no-index $wheel[0].FullName
        }

        Push-Location $verificationRoot
        try {
            $installedCommand = Join-Path $installRoot "Scripts\mojit.exe"
            $installedHelp = @(& $installedCommand -h)
            if (
                $LASTEXITCODE -ne 0 -or
                ($installedHelp -join "`n") -notmatch "--scene NAME" -or
                ($installedHelp -join "`n") -notmatch "Configuration precedence"
            ) {
                throw "Installed help smoke failed"
            }
            $effects = @(& $installedCommand --list-effects)
            if ($LASTEXITCODE -ne 0 -or ($effects -join ",") -ne "chromatic,glitch,neon,pulse") {
                throw "Installed effect listing smoke failed"
            }
            $scenes = @(& $installedCommand --list-scenes)
            if ($LASTEXITCODE -ne 0 -or ($scenes -join ",") -ne "rainy-night,snowfall,space") {
                throw "Installed scene listing smoke failed"
            }
            Invoke-Checked "installed scene config/render smoke" {
                & $installedPython (Join-Path $PSScriptRoot "source_smoke.py")
            }
        } finally {
            Pop-Location
        }

        if (Get-Command git -ErrorAction SilentlyContinue) {
            Invoke-Checked "Git whitespace check" { & git diff --check }
        }
    } finally {
        Pop-Location
    }
} finally {
    if (Test-Path -LiteralPath $verificationRoot) {
        Remove-Item -LiteralPath $verificationRoot -Recurse -Force
    }
}

Write-Host "Source verification passed"
