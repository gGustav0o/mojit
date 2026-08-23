[CmdletBinding()]
param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$archive = Join-Path $projectRoot "vendor\fribidi\source\fribidi-1.0.16.tar.xz"
$expectedSource = "1b1cde5b235d40479e91be2f0e88a309e3214c8ab470ec8a2744d82a5a9ea05c"
$expectedBinary = "4283ba30461395fdf46399b2665176e6f41d11bc7bf6977188120152fde31fd2"
$workRoot = Join-Path $projectRoot "build\fribidi-release"
$sourceRoot = Join-Path $workRoot "source"
$buildA = Join-Path $workRoot "build-a"
$buildB = Join-Path $workRoot "build-b"
$destination = Join-Path $projectRoot "src\mojit\_native\win_amd64\libfribidi-0.dll"

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant() -ne $expectedSource) {
    throw "FriBiDi source archive checksum mismatch"
}
if (Test-Path -LiteralPath $workRoot) {
    $resolvedBuild = (Resolve-Path -LiteralPath (Join-Path $projectRoot "build")).Path
    $resolvedWork = (Resolve-Path -LiteralPath $workRoot).Path
    if (-not $resolvedWork.StartsWith($resolvedBuild + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove unexpected build path: $resolvedWork"
    }
    Remove-Item -LiteralPath $resolvedWork -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $sourceRoot | Out-Null
tar -xf $archive -C $sourceRoot
$source = Join-Path $sourceRoot "fribidi-1.0.16"

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$installation = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
if (-not $installation) { throw "Visual Studio x64 C++ toolchain not found" }
$vcvars = Join-Path $installation "VC\Auxiliary\Build\vcvars64.bat"
$pythonPath = (Resolve-Path (Join-Path $projectRoot $Python)).Path
$meson = Join-Path (Split-Path $pythonPath) "meson.exe"
$options = "--buildtype=release --default-library=shared -Ddocs=false -Dbin=false -Dtests=false -Ddeprecated=true -Dc_link_args=/Brepro"

foreach ($build in @($buildA, $buildB)) {
    $command = "call `"$vcvars`" >nul && `"$meson`" setup `"$build`" `"$source`" $options && `"$meson`" compile -C `"$build`""
    & cmd.exe /d /s /c $command
    if ($LASTEXITCODE -ne 0) { throw "FriBiDi build failed" }
}
$dllA = Join-Path $buildA "lib\fribidi-0.dll"
$dllB = Join-Path $buildB "lib\fribidi-0.dll"
$hashA = (Get-FileHash -Algorithm SHA256 -LiteralPath $dllA).Hash.ToLowerInvariant()
$hashB = (Get-FileHash -Algorithm SHA256 -LiteralPath $dllB).Hash.ToLowerInvariant()
if ($hashA -ne $hashB -or $hashA -ne $expectedBinary) {
    throw "FriBiDi reproducibility/hash failure: $hashA / $hashB"
}
$inspect = "call `"$vcvars`" >nul && dumpbin /headers /dependents /exports `"$dllA`""
$dump = (& cmd.exe /d /s /c $inspect) -join "`n"
if ($LASTEXITCODE -ne 0 -or $dump -notmatch "8664 machine \(x64\)" -or $dump -notmatch "fribidi_log2vis") {
    throw "FriBiDi PE architecture/export inspection failed"
}
$allowed = @("VCRUNTIME140.dll", "api-ms-win-crt-heap-l1-1-0.dll", "api-ms-win-crt-stdio-l1-1-0.dll", "api-ms-win-crt-runtime-l1-1-0.dll", "KERNEL32.dll")
$dependencies = [regex]::Matches($dump, "(?m)^\s{4}([A-Za-z0-9_.-]+\.dll)\s*$") | ForEach-Object { $_.Groups[1].Value }
if (@($dependencies | Where-Object { $_ -notin $allowed }).Count -ne 0) {
    throw "Unexpected FriBiDi dependencies: $($dependencies -join ', ')"
}
Copy-Item -LiteralPath $dllA -Destination $destination -Force
Write-Host "Verified reproducible FriBiDi: $hashA"
