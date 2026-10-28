<#
.SYNOPSIS
    Builds optimized standalone executables for TXA toolchain using PyInstaller.

.EXAMPLE
    pwsh tools/packaging/build.ps1
#>
[CmdletBinding()]
param(
    [string]$DistDir = "dist",
    [switch]$Clean
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$toolsDir = Split-Path -Parent $scriptDir
Set-Location $toolsDir

Write-Host "-> TXA Packaging Build: Preparing executables..." -ForegroundColor Cyan

if ($Clean -and (Test-Path $DistDir)) {
    Remove-Item -Recurse -Force $DistDir
}

$versionInfo = Join-Path $scriptDir "version_info.txt"
$tools = @('txapm', 'txacreate', 'txacli', 'txaci')

foreach ($tool in $tools) {
    Write-Host "  Building $tool.exe..." -ForegroundColor Yellow
    $entry = "packaging/$tool.py"
    $args = @(
        '--noconfirm',
        '--onefile',
        '--console',
        '--name', $tool,
        '--distpath', $DistDir,
        '--workpath', "build/$tool",
        '--specpath', "build",
        '--collect-data', 'txa'
    )
    if (Test-Path $versionInfo) {
        $args += @('--version-file', $versionInfo)
    }
    $args += $entry

    & pyinstaller @args
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to build $tool.exe (exit code: $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
    Write-Host "  [ok] $DistDir/$tool.exe ready." -ForegroundColor Green
}

Write-Host "`n✓ All TXA standalone binaries built successfully into '$DistDir'!" -ForegroundColor Green

