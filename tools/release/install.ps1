[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$Wheelhouse = $PSScriptRoot,
    [string]$InstallRoot = "",
    [ValidateSet("User", "Process", "None")]
    [string]$PathScope = "User",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$Product = "mojit"
$Version = "1.0.0"
$MarkerName = ".mojit-install.json"
$ManifestName = "WHEELHOUSE_SHA256SUMS.txt"

function Get-NormalizedPath([string]$Path) {
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ($fullPath -eq [IO.Path]::GetPathRoot($fullPath)) { return $fullPath }
    return $fullPath.TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
}

function Get-PathKey([string]$Path) {
    $candidate = $Path.Trim().Trim('"')
    try {
        return (Get-NormalizedPath $candidate).ToUpperInvariant()
    } catch {
        return $candidate.TrimEnd("\", "/").ToUpperInvariant()
    }
}

function Set-MojitPathEntry(
    [string]$Entry,
    [bool]$Present,
    [string]$Scope
) {
    if ($Scope -eq "None") { return $false }
    $target = [EnvironmentVariableTarget]::$Scope
    $current = [Environment]::GetEnvironmentVariable("Path", $target)
    $entryKey = Get-PathKey $Entry
    $entries = @(
        $current -split ";" |
            Where-Object { $_.Trim() -and (Get-PathKey $_) -ne $entryKey }
    )
    $updated = if ($Present) { @($Entry) + $entries } else { $entries }
    $value = $updated -join ";"
    if ($value -ne $current) {
        [Environment]::SetEnvironmentVariable("Path", $value, $target)
        return $true
    }
    return $false
}

function Publish-EnvironmentChange {
    if (-not ("MojitEnvironmentBroadcast" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class MojitEnvironmentBroadcast {
    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr hWnd, uint message, UIntPtr wParam, string lParam,
        uint flags, uint timeout, out UIntPtr result);
}
"@
    }
    $result = [UIntPtr]::Zero
    [void][MojitEnvironmentBroadcast]::SendMessageTimeout(
        [IntPtr]0xffff,
        0x001a,
        [UIntPtr]::Zero,
        "Environment",
        0x0002,
        5000,
        [ref]$result
    )
}

function Assert-SafeInstallRoot([string]$Root) {
    $normalized = Get-NormalizedPath $Root
    if ([IO.Path]::GetPathRoot($normalized) -eq $normalized) {
        throw "Refusing to use a filesystem root as InstallRoot: $normalized"
    }
    return $normalized
}

function Get-OwnedInstallation([string]$Root) {
    $markerPath = Join-Path $Root $MarkerName
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw "Refusing to modify an unowned installation directory: $Root"
    }
    try {
        $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding utf8 | ConvertFrom-Json
    } catch {
        throw "Invalid mojit installation marker: $markerPath"
    }
    if ($marker.product -ne $Product -or $marker.schema -ne 1) {
        throw "Invalid mojit installation marker: $markerPath"
    }
    return $marker
}

function Assert-Wheelhouse([string]$Root) {
    $manifestPath = Join-Path $Root $ManifestName
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Wheelhouse checksum manifest is missing: $manifestPath"
    }

    $expected = @{}
    foreach ($line in Get-Content -LiteralPath $manifestPath -Encoding ascii) {
        if ($line -notmatch "^([0-9a-f]{64})  ([^\\/]+)$") {
            throw "Malformed wheelhouse checksum line: $line"
        }
        if ($expected.ContainsKey($Matches[2])) {
            throw "Duplicate wheelhouse checksum entry: $($Matches[2])"
        }
        $expected[$Matches[2]] = $Matches[1]
    }

    $files = @(
        Get-ChildItem -LiteralPath $Root -File |
            Where-Object { $_.Name -ne $ManifestName }
    )
    $actualNames = @($files | ForEach-Object { $_.Name } | Sort-Object)
    $expectedNames = @($expected.Keys | Sort-Object)
    if (($actualNames -join "`n") -ne ($expectedNames -join "`n")) {
        throw "Wheelhouse inventory does not match its checksum manifest"
    }
    foreach ($file in $files) {
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
        if ($actual -ne $expected[$file.Name]) {
            throw "Wheelhouse checksum mismatch: $($file.Name)"
        }
    }

    $applicationWheels = @(
        $files | Where-Object { $_.Name -eq "mojit-$Version-py3-none-win_amd64.whl" }
    )
    if ($applicationWheels.Count -ne 1) {
        throw "Wheelhouse must contain exactly one mojit $Version wheel"
    }
}

function Resolve-CompatiblePython([string]$Requested) {
    if ($Requested) {
        if (Test-Path -LiteralPath $Requested -PathType Leaf) {
            $candidate = (Resolve-Path -LiteralPath $Requested).Path
        } else {
            $command = Get-Command $Requested -ErrorAction Stop
            $candidate = $command.Source
        }
    } else {
        $candidate = ""
        $launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
        if ($launcher) {
            foreach ($version in @("3.14", "3.13", "3.12", "3.11")) {
                $output = (& $launcher.Source "-$version" -c "import sys; print(sys.executable)" 2>$null)
                if ($LASTEXITCODE -eq 0 -and $output) {
                    $candidate = ($output | Select-Object -Last 1).Trim()
                    break
                }
            }
        }
        if (-not $candidate) {
            $pathPython = Get-Command "python.exe" -ErrorAction SilentlyContinue
            if ($pathPython) { $candidate = $pathPython.Source }
        }
        if (-not $candidate) {
            throw "No Python installation was found; use -Python to select one"
        }
    }

    $probe = (& $candidate -c 'import struct,sys; print(str(sys.version_info.major)+"."+str(sys.version_info.minor)+"|"+str(struct.calcsize("P")*8))')
    if ($LASTEXITCODE -ne 0 -or -not $probe) {
        throw "Cannot execute Python interpreter: $candidate"
    }
    $parts = ($probe | Select-Object -Last 1).Trim().Split("|")
    if ($parts.Count -ne 2 -or $parts[0] -notin @("3.11", "3.12", "3.13", "3.14")) {
        throw "mojit requires CPython 3.11-3.14; found $($parts[0])"
    }
    if ($parts[1] -ne "64") {
        throw "mojit requires a 64-bit CPython interpreter"
    }
    return (Get-NormalizedPath $candidate)
}

if (-not $InstallRoot) {
    $localMarker = Join-Path $PSScriptRoot $MarkerName
    if ($Uninstall -and (Test-Path -LiteralPath $localMarker -PathType Leaf)) {
        $InstallRoot = $PSScriptRoot
    } else {
        if (-not $env:LOCALAPPDATA) { throw "LOCALAPPDATA is not defined" }
        $InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\mojit"
    }
}

$installPath = Assert-SafeInstallRoot $InstallRoot
$scriptsPath = Join-Path $installPath "Scripts"

if ($Uninstall) {
    [void](Get-OwnedInstallation $installPath)
    $currentLocation = Get-NormalizedPath ((Get-Location).Path)
    if ($currentLocation -eq $installPath -or $currentLocation.StartsWith($installPath + "\")) {
        Set-Location ([IO.Path]::GetTempPath())
    }
    Remove-Item -LiteralPath $installPath -Recurse -Force
    if ($PathScope -ne "None") {
        [void](Set-MojitPathEntry $scriptsPath $false $PathScope)
        [void](Set-MojitPathEntry $scriptsPath $false "Process")
        if ($PathScope -eq "User") { Publish-EnvironmentChange }
    }
    Write-Host "mojit $Version was uninstalled from $installPath"
    exit 0
}

$wheelhousePath = (Resolve-Path -LiteralPath $Wheelhouse).Path
Assert-Wheelhouse $wheelhousePath
$created = $false
$pathAdded = $false

try {
    if (Test-Path -LiteralPath $installPath) {
        [void](Get-OwnedInstallation $installPath)
        $pythonPath = Join-Path $scriptsPath "python.exe"
        if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
            throw "Existing mojit installation has no Python interpreter: $pythonPath"
        }
    } else {
        $parent = Split-Path $installPath -Parent
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        $pythonPath = Resolve-CompatiblePython $Python
        $created = $true
        & $pythonPath -m venv $installPath
        if ($LASTEXITCODE -ne 0) { throw "Failed to create the mojit virtual environment" }
        $pythonPath = Join-Path $scriptsPath "python.exe"
    }

    & $pythonPath -m pip install --disable-pip-version-check --no-index --find-links $wheelhousePath --upgrade --force-reinstall "$Product==$Version"
    if ($LASTEXITCODE -ne 0) { throw "Offline mojit installation failed" }

    $pythonVersion = (& $pythonPath -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" | Select-Object -Last 1).Trim()
    [ordered]@{
        schema = 1
        product = $Product
        version = $Version
        python = $pythonVersion
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $installPath $MarkerName) -Encoding utf8
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $installPath "install.ps1") -Force

    if ($PathScope -ne "None") {
        $pathAdded = Set-MojitPathEntry $scriptsPath $true $PathScope
        [void](Set-MojitPathEntry $scriptsPath $true "Process")
        if ($PathScope -eq "User") { Publish-EnvironmentChange }
    }

    Push-Location ([IO.Path]::GetTempPath())
    try {
        $expectedCommand = Join-Path $scriptsPath "mojit.exe"
        if ($PathScope -eq "None") {
            $commandPath = $expectedCommand
        } else {
            $command = Get-Command "mojit.exe" -ErrorAction Stop
            if ((Get-NormalizedPath $command.Source) -ne (Get-NormalizedPath $expectedCommand)) {
                throw "The installed mojit command is shadowed by $($command.Source)"
            }
            $commandPath = "mojit.exe"
        }
        $effects = (& $commandPath --list-effects) -join "`n"
        if ($LASTEXITCODE -ne 0 -or $effects -notmatch "neon") {
            throw "Installed mojit command smoke test failed"
        }
    } finally {
        Pop-Location
    }
} catch {
    if ($pathAdded) {
        [void](Set-MojitPathEntry $scriptsPath $false $PathScope)
        [void](Set-MojitPathEntry $scriptsPath $false "Process")
    }
    if ($created -and (Test-Path -LiteralPath $installPath)) {
        Remove-Item -LiteralPath $installPath -Recurse -Force
    }
    throw
}

Write-Host "mojit $Version was installed successfully"
Write-Host "Installation: $installPath"
Write-Host "Command:      $scriptsPath\mojit.exe"
if ($PathScope -eq "User") {
    Write-Host "Restart WezTerm once, then run: mojit --list-effects"
}
