<#
.SYNOPSIS
    Installs the TXA toolchain (txapm, txacreate) for the current user.

.DESCRIPTION
    One-liner (PowerShell 5.1 or 7+, no admin rights needed):

        irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1 | iex

    With parameters:

        & ([scriptblock]::Create((irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1))) -Version 1.0.0

    The installer asks for its language (English / Vietnamese) before it starts. Skip the question with -Lang en|vi
    (or TXA_LANG), e.g. for unattended installs:

        & ([scriptblock]::Create((irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1))) -Lang vi

    Environment overrides (useful with the iex form): TXA_VERSION, TXA_HOME, TXA_REPO, TXA_LANG.

    Layout created under %LOCALAPPDATA%\TXA (or TXA_HOME):
        bin\      txapm.exe, txacreate.exe   (added to the user PATH)
        logs\     installer logs written by txapm
        state\    installed.json
        config.json, credentials.bin (DPAPI-encrypted, created when txacreate first opens a PR)
#>
[CmdletBinding()]
param(
    [string]$Version = $(if ($env:TXA_VERSION) { $env:TXA_VERSION } else { 'latest' }),
    [string]$InstallDir = $(if ($env:TXA_HOME) { $env:TXA_HOME } else { Join-Path $env:LOCALAPPDATA 'TXA' }),
    [string]$Repo = $(if ($env:TXA_REPO) { $env:TXA_REPO } else { 'TXAVL/txa-repo' }),
    [ValidateSet('', 'en', 'vi')][string]$Lang = $(if ($env:TXA_LANG) { ($env:TXA_LANG -split '[-_]')[0].ToLowerInvariant() } else { '' }),
    [switch]$NoPath,
    [switch]$Uninstall
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Invoke-WebRequest is far faster without the progress bar on 5.1

function Write-Step([string]$Message) { Write-Host "-> $Message" -ForegroundColor Cyan }
function Write-Done([string]$Message) { Write-Host "[ok] $Message" -ForegroundColor Green }

function Get-UserPath {
    # Read the raw value so entries such as %USERPROFILE%\bin are not expanded and lost.
    $key = Get-Item -LiteralPath 'HKCU:\Environment'
    return [string]$key.GetValue('Path', '', 'DoNotExpandEnvironmentNames')
}

function Set-UserPath([string]$Value) {
    New-ItemProperty -LiteralPath 'HKCU:\Environment' -Name 'Path' -Value $Value -PropertyType ExpandString -Force | Out-Null
}

function Test-SamePath([string]$A, [string]$B) {
    return ([Environment]::ExpandEnvironmentVariables($A).TrimEnd('\')) -ieq ($B.TrimEnd('\'))
}


# ------------------------------------------------------------------ language
$Strings = @{
    en = @{
        notWindows = 'TXA installs Windows software; run this script on Windows.'
        removingPath = 'Removing {0} from the user PATH'
        deleting = 'Deleting {0}'
        removed = 'TXA removed. Open a new terminal to refresh PATH.'
        badArch = 'Unsupported CPU architecture ''{0}'' - TXA ships x64 and arm64 builds.'
        lookup = 'Looking up TXA {0} in {1}'
        noArm = '   no native arm64 build in this release - using x64 (runs under emulation)'
        missingAsset = 'Release {0} is missing txa-windows-{1}.zip or SHA256SUMS.txt'
        downloading = 'Downloading {0} ({1} MB) from {2}'
        noSum = 'SHA256SUMS.txt has no entry for {0}'
        badSum = 'Checksum mismatch for {0}: expected {1}, got {2}'
        sumOk = 'SHA-256 verified ({0})'
        noExe = 'Archive does not contain txapm.exe'
        noReplace = 'Could not replace {0} - close any running txapm/txacreate and retry. ({1})'
        installedTo = 'Installed to {0}'
        pathAdded = 'Added {0} to the user PATH'
        pathHas = 'PATH already contains the TXA bin folder'
        ready = '{0} is ready'
        newTerminal = '  OPEN A NEW TERMINAL FIRST so the new PATH is loaded, then try:'
        hPm = 'txapm - install and manage software'
        hSrc = 'txapm source - extra package repositories'
        hCli = 'txacli - fast WinGet importer, PC scanner & API builder'
        hCreate = 'txacreate - publish software to the TXA repository'
        hEx = 'Examples'
        noLogin = '  (no login needed up front: GitHub access is asked only at the fork step)'
        portable = '(portable: unpacked + added to your PATH, no admin needed)'
        npmNote = '(npm ships with Node.js)'
        help = '  Help for any command:  txapm <command> --help | txacli --help | txacreate --help      Docs: https://github.com/{0}'
        pickTitle = 'Language'
    }
    vi = @{
        notWindows = 'TXA c\u00e0i ph\u1ea7n m\u1ec1m cho Windows; h\u00e3y ch\u1ea1y script n\u00e0y tr\u00ean Windows.'
        removingPath = '\u0110ang g\u1ee1 {0} kh\u1ecfi PATH c\u1ee7a ng\u01b0\u1eddi d\u00f9ng'
        deleting = '\u0110ang xo\u00e1 {0}'
        removed = '\u0110\u00e3 g\u1ee1 TXA. M\u1edf terminal m\u1edbi \u0111\u1ec3 PATH \u0111\u01b0\u1ee3c c\u1eadp nh\u1eadt.'
        badArch = 'Ki\u1ebfn tr\u00fac CPU ''{0}'' ch\u01b0a \u0111\u01b0\u1ee3c h\u1ed7 tr\u1ee3 - TXA c\u00f3 b\u1ea3n x64 v\u00e0 arm64.'
        lookup = '\u0110ang t\u00ecm TXA {0} trong {1}'
        noArm = '   b\u1ea3n n\u00e0y ch\u01b0a c\u00f3 arm64 g\u1ed1c - d\u00f9ng b\u1ea3n x64 (ch\u1ea1y qua gi\u1ea3 l\u1eadp)'
        missingAsset = 'B\u1ea3n ph\u00e1t h\u00e0nh {0} thi\u1ebfu txa-windows-{1}.zip ho\u1eb7c SHA256SUMS.txt'
        downloading = '\u0110ang t\u1ea3i {0} ({1} MB) t\u1eeb {2}'
        noSum = 'SHA256SUMS.txt kh\u00f4ng c\u00f3 d\u00f2ng cho {0}'
        badSum = 'SHA-256 c\u1ee7a {0} kh\u00f4ng kh\u1edbp: c\u1ea7n {1}, nh\u1eadn \u0111\u01b0\u1ee3c {2}'
        sumOk = '\u0110\u00e3 ki\u1ec3m tra SHA-256 ({0})'
        noExe = 'G\u00f3i t\u1ea3i v\u1ec1 kh\u00f4ng ch\u1ee9a txapm.exe'
        noReplace = 'Kh\u00f4ng thay \u0111\u01b0\u1ee3c {0} - h\u00e3y \u0111\u00f3ng txapm/txacreate \u0111ang ch\u1ea1y r\u1ed3i th\u1eed l\u1ea1i. ({1})'
        installedTo = '\u0110\u00e3 c\u00e0i v\u00e0o {0}'
        pathAdded = '\u0110\u00e3 th\u00eam {0} v\u00e0o PATH c\u1ee7a ng\u01b0\u1eddi d\u00f9ng'
        pathHas = 'PATH \u0111\u00e3 c\u00f3 th\u01b0 m\u1ee5c bin c\u1ee7a TXA'
        ready = '{0} \u0111\u00e3 s\u1eb5n s\u00e0ng'
        newTerminal = '  H\u00c3Y M\u1ede TERMINAL M\u1edaI \u0111\u1ec3 n\u1ea1p PATH m\u1edbi, r\u1ed3i th\u1eed:'
        hPm = 'txapm - c\u00e0i v\u00e0 qu\u1ea3n l\u00fd ph\u1ea7n m\u1ec1m'
        hSrc = 'txapm source - th\u00eam kho ph\u1ea7n m\u1ec1m kh\u00e1c'
        hCli = 'txacli - c\u00f4ng c\u1ee5 nhanh: t\u00ecm/import WinGet, qu\u00e9t m\u00e1y v\u00e0 t\u1ea1o API'
        hCreate = 'txacreate - \u0111\u00f3ng g\u00f3p ph\u1ea7n m\u1ec1m v\u00e0o kho TXA'
        hEx = 'V\u00ed d\u1ee5'
        noLogin = '  (kh\u00f4ng c\u1ea7n \u0111\u0103ng nh\u1eadp tr\u01b0\u1edbc: ch\u1ec9 xin quy\u1ec1n GitHub \u1edf b\u01b0\u1edbc fork)'
        portable = '(b\u1ea3n portable: gi\u1ea3i n\u00e9n v\u00e0 th\u00eam v\u00e0o PATH, kh\u00f4ng c\u1ea7n quy\u1ec1n admin)'
        npmNote = '(npm \u0111i k\u00e8m Node.js)'
        help = '  Tr\u1ee3 gi\u00fap m\u1ecdi l\u1ec7nh:  txapm <command> --help | txacli --help | txacreate --help      T\u00e0i li\u1ec7u: https://github.com/{0}'
        pickTitle = 'Ng\u00f4n ng\u1eef'
    }
}
function T([string]$Key, [object[]]$Args2) {
    $value = $Strings[$script:UiLang][$Key]
    if ($script:UiLang -eq 'vi') { $value = [regex]::Unescape($value) }  # vi text is stored as \uXXXX so this file stays ASCII
    if ($Args2) { return ($value -f $Args2) }
    return $value
}

function Select-Language {
    try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }  # so Vietnamese letters in the question display correctly
    if ($Lang -in @('en', 'vi')) { return $Lang }
    $options = @(
        @{ Code = 'en'; Label = '1) English' },
        @{ Code = 'vi'; Label = ('2) Ti' + [regex]::Unescape('\u1ebfng Vi\u1ec7t')) }
    )
    $selected = if ((Get-UICulture).Name -like 'vi*') { 1 } else { 0 }
    $title = '  Language / ' + [regex]::Unescape('Ng\u00f4n ng\u1eef')
    $hint  = ' (' + [regex]::Unescape('d\u00f9ng \u2191/\u2193 ho\u1eb7c ph\u00edm 1-2, Enter \u0111\u1ec3 ch\u1ecdn') + ')'

    try {
        if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) { throw 'non-interactive' }
        Write-Host ''
        Write-Host "$title$hint" -ForegroundColor Cyan
        for ($i = 0; $i -lt $options.Count; $i++) { Write-Host '' }
        $top = [Console]::CursorTop - $options.Count
        while ($true) {
            for ($i = 0; $i -lt $options.Count; $i++) {
                [Console]::SetCursorPosition(0, $top + $i)
                $isSel = ($i -eq $selected)
                $marker = if ($isSel) { [regex]::Unescape('  \u203a ') } else { '    ' }
                $text = ($marker + $options[$i].Label).PadRight(44)
                if ($isSel) {
                    Write-Host $text -ForegroundColor Cyan -NoNewline
                } else {
                    Write-Host $text -ForegroundColor Gray -NoNewline
                }
            }
            [Console]::SetCursorPosition(0, $top + $options.Count)
            $key = [Console]::ReadKey($true)
            switch ($key.Key) {
                'UpArrow'    { $selected = ($selected + $options.Count - 1) % $options.Count }
                'DownArrow'  { $selected = ($selected + 1) % $options.Count }
                'LeftArrow'  { $selected = ($selected + $options.Count - 1) % $options.Count }
                'RightArrow' { $selected = ($selected + 1) % $options.Count }
                'Enter'      { Write-Host ''; return $options[$selected].Code }
                default {
                    if ($key.KeyChar -eq '1') { $selected = 0 }
                    elseif ($key.KeyChar -eq '2') { $selected = 1 }
                    elseif ($key.KeyChar -in @('e', 'E')) { $selected = 0 }
                    elseif ($key.KeyChar -in @('v', 'V')) { $selected = 1 }
                }
            }
        }
    } catch {
        $defaultNum = $selected + 1
        try {
            Write-Host ''
            Write-Host $title -ForegroundColor Cyan
            Write-Host '    1) English'
            Write-Host ('    2) Ti' + [regex]::Unescape('\u1ebfng Vi\u1ec7t'))
            $answer = Read-Host "  [1-2] (Enter = $defaultNum)"
        } catch { return $options[$selected].Code }
        if ($answer -match '^\s*(2|vi|v)') { return 'vi' }
        if ($answer -match '^\s*(1|en|e)') { return 'en' }
        return $options[$selected].Code
    }
}
$script:UiLang = Select-Language

# Persist the chosen UI language immediately into user environment & config.json
[Environment]::SetEnvironmentVariable('TXA_LANG', $script:UiLang, 'User')
$env:TXA_LANG = $script:UiLang
try {
    if (-not (Test-Path -LiteralPath $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    $cfgPath = Join-Path $InstallDir 'config.json'
    $cfgObj = if (Test-Path -LiteralPath $cfgPath) {
        Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        New-Object PSObject
    }
    $cfgObj | Add-Member -MemberType NoteProperty -Name 'lang' -Value $script:UiLang -Force
    ($cfgObj | ConvertTo-Json -Depth 10) | Set-Content -LiteralPath $cfgPath -Encoding UTF8
} catch { }

if ([Environment]::OSVersion.Platform -ne 'Win32NT') {
    throw (T 'notWindows')
}

$BinDir = Join-Path $InstallDir 'bin'

# ------------------------------------------------------------------ uninstall
if ($Uninstall) {
    Write-Step (T 'removingPath' $BinDir)
    $entries = @((Get-UserPath) -split ';' | Where-Object { $_ -and -not (Test-SamePath $_ $BinDir) })
    Set-UserPath ($entries -join ';')
    [Environment]::SetEnvironmentVariable('TXA_HOME', $null, 'User')  # also broadcasts the change
    [Environment]::SetEnvironmentVariable('TXA_LANG', $null, 'User')
    if (Test-Path -LiteralPath $InstallDir) {
        Write-Step (T 'deleting' $InstallDir)
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
    }
    Write-Done (T 'removed')
    return
}

# ------------------------------------------------------------------ resolve release
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$headers = @{ 'User-Agent' = 'txa-install'; 'Accept' = 'application/vnd.github+json' }

$arch = switch ($env:PROCESSOR_ARCHITECTURE) {
    'ARM64' { 'arm64' }
    'AMD64' { 'x64' }
    default { throw (T 'badArch' $env:PROCESSOR_ARCHITECTURE) }
}
if ($env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { $arch = 'arm64' }

$releaseUrl = if ($Version -eq 'latest') {
    "https://api.github.com/repos/$Repo/releases/latest"
} else {
    "https://api.github.com/repos/$Repo/releases/tags/v$($Version.TrimStart('v'))"
}
Write-Step (T 'lookup' $Version, $Repo)
$release = $null
$asset = $null
$sums = $null
for ($attempt = 1; $attempt -le 4; $attempt++) {
    $release = Invoke-RestMethod -Uri $releaseUrl -Headers $headers
    $asset = $release.assets | Where-Object { $_.name -eq "txa-windows-$arch.zip" } | Select-Object -First 1
    if (-not $asset -and $arch -eq 'arm64') {
        Write-Host (T 'noArm') -ForegroundColor Yellow
        $arch = 'x64'
        $asset = $release.assets | Where-Object { $_.name -eq 'txa-windows-x64.zip' } | Select-Object -First 1
    }
    $sums = $release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
    if ($asset -and $sums) { break }
    if ($attempt -lt 4) { Start-Sleep -Seconds 3 }
}
if (-not $asset -or -not $sums) { throw (T 'missingAsset' $release.tag_name, $arch) }

# ------------------------------------------------------------------ download + verify
$staging = Join-Path ([IO.Path]::GetTempPath()) ("txa-install-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null
try {
    $zip = Join-Path $staging $asset.name
    Write-Step (T 'downloading' $asset.name, ([Math]::Round($asset.size / 1MB, 1)), $release.tag_name)
    $hasCurl = (Get-Command curl.exe -ErrorAction SilentlyContinue) -ne $null
    if ($hasCurl) {
        & curl.exe -fL --retry 3 --retry-delay 2 -s -o $zip $asset.browser_download_url
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $zip)) {
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -Headers $headers -UseBasicParsing
        }
    } else {
        try {
            $wc = New-Object System.Net.WebClient
            $wc.Headers.Add('User-Agent', 'txa-install')
            $wc.DownloadFile($asset.browser_download_url, $zip)
        } catch {
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -Headers $headers -UseBasicParsing
        }
    }
    $sumsText = (Invoke-WebRequest -Uri $sums.browser_download_url -Headers $headers -UseBasicParsing).Content
    if ($sumsText -is [byte[]]) { $sumsText = [Text.Encoding]::UTF8.GetString($sumsText) }

    $expected = $null
    foreach ($line in ($sumsText -split "`n")) {
        $parts = $line.Trim() -split '\s+', 2
        if ($parts.Count -eq 2 -and $parts[1].TrimStart('*') -eq $asset.name) { $expected = $parts[0].ToUpperInvariant() }
    }
    if (-not $expected) { throw (T 'noSum' $asset.name) }
    $actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actual -ne $expected) { throw (T 'badSum' $asset.name, $expected, $actual) }
    Write-Done (T 'sumOk' $actual)

    # -------------------------------------------------------------- lay out the install folder
    foreach ($dir in @($InstallDir, (Join-Path $InstallDir 'logs'), (Join-Path $InstallDir 'state'))) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $newBin = Join-Path $InstallDir 'bin.new'
    $oldBin = Join-Path $InstallDir 'bin.old'
    foreach ($dir in @($newBin, $oldBin)) {
        if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
    }
    Expand-Archive -LiteralPath $zip -DestinationPath $newBin -Force
    if (-not (Test-Path -LiteralPath (Join-Path $newBin 'txapm.exe'))) { throw (T 'noExe') }
    try {
        if (Test-Path -LiteralPath $BinDir) { Rename-Item -LiteralPath $BinDir -NewName 'bin.old' }
        Rename-Item -LiteralPath $newBin -NewName 'bin'
    } catch {
        throw (T 'noReplace' $BinDir, $_.Exception.Message)
    }
    if (Test-Path -LiteralPath $oldBin) { Remove-Item -LiteralPath $oldBin -Recurse -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -LiteralPath $BinDir -Recurse | Unblock-File -ErrorAction SilentlyContinue
    Write-Done (T 'installedTo' $BinDir)
} finally {
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
}

# ------------------------------------------------------------------ PATH + TXA_HOME
if (-not $NoPath) {
    $current = Get-UserPath
    $entries = @($current -split ';' | Where-Object { $_ })
    if (-not ($entries | Where-Object { Test-SamePath $_ $BinDir })) {
        Set-UserPath ((@($entries) + $BinDir) -join ';')
        Write-Done (T 'pathAdded' $BinDir)
    } else {
        Write-Done (T 'pathHas')
    }
    if (-not (($env:Path -split ';') | Where-Object { $_ -and (Test-SamePath $_ $BinDir) })) {
        $env:Path = "$env:Path;$BinDir"
    }
}
# Setting a user variable broadcasts WM_SETTINGCHANGE, so new terminals pick up PATH too.
[Environment]::SetEnvironmentVariable('TXA_HOME', $InstallDir, 'User')
$env:TXA_HOME = $InstallDir
[Environment]::SetEnvironmentVariable('TXA_LANG', $script:UiLang, 'User')
$env:TXA_LANG = $script:UiLang

# Persist the chosen UI language into %LOCALAPPDATA%\TXA\config.json for txapm / txacli / txacreate
$cfgPath = Join-Path $InstallDir 'config.json'
try {
    $cfgObj = if (Test-Path -LiteralPath $cfgPath) {
        Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        New-Object PSObject
    }
    $cfgObj | Add-Member -MemberType NoteProperty -Name 'lang' -Value $script:UiLang -Force
    ($cfgObj | ConvertTo-Json -Depth 10) | Set-Content -LiteralPath $cfgPath -Encoding UTF8
} catch { }

$installed = & (Join-Path $BinDir 'txapm.exe') --version
Write-Done (T 'ready' $installed)

function Write-Row([string]$Command, [string]$Meaning) {
    Write-Host ('  {0,-46}' -f $Command) -NoNewline -ForegroundColor Yellow
    Write-Host $Meaning
}
function Write-Heading([string]$Text) {
    Write-Host ''
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host ('  ' + ('-' * 78)) -ForegroundColor DarkGray
}
function Write-Table($Items) {
    $col = if ($script:UiLang -eq 'vi') { 2 } else { 1 }
    foreach ($item in $Items) {
        $meaning = $item[$col]
        if ($script:UiLang -eq 'vi') { $meaning = [regex]::Unescape($meaning) }
        Write-Row $item[0] $meaning
    }
}

Write-Host ''
Write-Host (T 'newTerminal') -ForegroundColor Green

Write-Heading (T 'hPm')
Write-Table @(
    @('txapm search notepad', 'find packages (name, alias, tag)', 't\u00ecm ph\u1ea7n m\u1ec1m (t\u00ean, alias, th\u1ebb)'),
    @('txapm show TXAVL.HelloTool', 'details; add --versions to list all versions', 'xem chi ti\u1ebft; th\u00eam --versions \u0111\u1ec3 li\u1ec7t k\u00ea m\u1ecdi b\u1ea3n'),
    @('txapm install TXAVL.HelloTool', 'download, verify SHA-256, silent install', 't\u1ea3i, ki\u1ec3m tra SHA-256, c\u00e0i im l\u1eb7ng'),
    @('txapm install hellotool --version 1.4.2', 'a specific version (an alias works too)', 'c\u00e0i \u0111\u00fang m\u1ed9t phi\u00ean b\u1ea3n (d\u00f9ng alias c\u0169ng \u0111\u01b0\u1ee3c)'),
    @('txapm install <id> --progress', 'unattended, installer progress window shown', 't\u1ef1 \u0111\u1ed9ng, v\u1eabn hi\u1ec7n c\u1eeda s\u1ed5 ti\u1ebfn tr\u00ecnh c\u1ee7a b\u1ed9 c\u00e0i'),
    @('txapm install <id> --interactive', 'the installer''s normal wizard', 'd\u00f9ng giao di\u1ec7n c\u00e0i \u0111\u1eb7t g\u1ed1c c\u1ee7a b\u1ed9 c\u00e0i'),
    @('txapm install <id> --download-only', 'only download + verify', 'ch\u1ec9 t\u1ea3i v\u1ec1 v\u00e0 ki\u1ec3m tra'),
    @('txapm install --manifest <folder>', 'test a manifest from disk before submitting it', 'th\u1eed m\u1ed9t manifest tr\u00ean m\u00e1y tr\u01b0\u1edbc khi g\u1eedi'),
    @('txapm list', 'packages installed through txapm', 'c\u00e1c g\u00f3i \u0111\u00e3 c\u00e0i b\u1eb1ng txapm'),
    @('txapm list --upgrade-available', 'only those with a newer version', 'ch\u1ec9 nh\u1eefng g\u00f3i c\u00f3 b\u1ea3n m\u1edbi'),
    @('txapm list --all', 'every program on this PC, matched to TXA', 'm\u1ecdi ch\u01b0\u01a1ng tr\u00ecnh tr\u00ean m\u00e1y, \u0111\u1ed1i chi\u1ebfu v\u1edbi kho TXA'),
    @('txapm upgrade --all', 'upgrade everything (or: upgrade <id>)', 'n\u00e2ng c\u1ea5p t\u1ea5t c\u1ea3 (ho\u1eb7c: upgrade <id>)'),
    @('txapm pin add <id>', 'hold a version; upgrade --all skips it', 'gi\u1eef nguy\u00ean phi\u00ean b\u1ea3n; upgrade --all s\u1ebd b\u1ecf qua'),
    @('txapm uninstall TXAVL.HelloTool', 'silent uninstall', 'g\u1ee1 c\u00e0i \u0111\u1eb7t im l\u1eb7ng'),
    @('txapm export pkgs.json', 'save the installed list', 'l\u01b0u danh s\u00e1ch \u0111\u00e3 c\u00e0i'),
    @('txapm import pkgs.json', 'reinstall everything on a new PC', 'c\u00e0i l\u1ea1i t\u1ea5t c\u1ea3 tr\u00ean m\u00e1y m\u1edbi'),
    @('txapm download <id> -d D:\setup', 'installer + manifest into a folder', 't\u1ea3i b\u1ed9 c\u00e0i v\u00e0 manifest v\u00e0o m\u1ed9t th\u01b0 m\u1ee5c'),
    @('txapm which <id>', 'show local install record, scope & paths', 'xem \u0111\u01b0\u1eddng d\u1eabn, ph\u1ea1m vi v\u00e0 th\u00f4ng tin g\u00f3i \u0111\u00e3 c\u00e0i'),
    @('txapm log [<id>] [-n 50]', 'list or view latest installer logs', 'li\u1ec7t k\u00ea ho\u1eb7c xem n\u1ed9i dung file log c\u00e0i \u0111\u1eb7t'),
    @('txapm clean [--all]', 'clean temporary installer cache & logs', 'd\u1ecdn d\u1eb9p b\u1ed9 c\u00e0i t\u1ea3i t\u1ea1m v\u00e0 file log'),
    @('txapm doctor', 'check system health, sources, WinGet & cache', 'ki\u1ec3m tra s\u1ee9c kho\u1ebb h\u1ec7 th\u1ed1ng, kho ngu\u1ed3n, WinGet v\u00e0 cache'),
    @('txapm lang [en|vi]', 'view or switch display language (en / vi)', 'xem ho\u1eb7c chuy\u1ec3n \u0111\u1ed5i ng\u00f4n ng\u1eef hi\u1ec3n th\u1ecb (en / vi)'),
    @('txapm wg search <query>', 'search packages directly on WinGet', 't\u00ecm ki\u1ebfm ph\u1ea7n m\u1ec1m tr\u1ef1c ti\u1ebfp tr\u00ean WinGet'),
    @('txapm wg install <id>', 'install package from WinGet via txapm', 'c\u00e0i g\u00f3i t\u1eeb WinGet th\u00f4ng qua txapm'),
    @('txapm wg -i', 'scan PC & import missing apps from WinGet', 'qu\u00e9t m\u00e1y v\u00e0 import c\u00e1c g\u00f3i ch\u01b0a c\u00f3 t\u1eeb WinGet'),
    @('txapm --info', 'version, paths, sources, account', 'phi\u00ean b\u1ea3n, \u0111\u01b0\u1eddng d\u1eabn, kho ngu\u1ed3n, t\u00e0i kho\u1ea3n')
)

Write-Heading (T 'hSrc')
Write-Table @(
    @('txapm source', 'list sources (txa is the official one)', 'li\u1ec7t k\u00ea kho ngu\u1ed3n (txa l\u00e0 kho ch\u00ednh th\u1ee9c)'),
    @('txapm source add corp https://h.vn/api/txa/v1', 'add an HTTPS source', 'th\u00eam kho ngu\u1ed3n HTTPS'),
    @('txapm source add lab D:\txa-repo', 'add a local or network folder', 'th\u00eam th\u01b0 m\u1ee5c tr\u00ean m\u00e1y ho\u1eb7c m\u1ea1ng n\u1ed9i b\u1ed9'),
    @('txapm source add corp <url> --token-env VAR', 'private source, token read from env VAR', 'kho ri\u00eang, token l\u1ea5y t\u1eeb bi\u1ebfn m\u00f4i tr\u01b0\u1eddng VAR'),
    @('txapm install <id> -s corp', 'use one source only', 'ch\u1ec9 d\u00f9ng m\u1ed9t kho ngu\u1ed3n'),
    @('txapm source disable|enable|remove <name>', 'switch off, on, or delete a source', 't\u1eaft, b\u1eadt ho\u1eb7c xo\u00e1 m\u1ed9t kho ngu\u1ed3n')
)

Write-Heading (T 'hCli')
Write-Table @(
    @('txacli -s <query>  (or: txacli search <q>)', 'search WinGet for matching packages', 't\u00ecm ki\u1ebfm g\u00f3i ph\u1ea7n m\u1ec1m tr\u00ean WinGet'),
    @('txacli <winget-id-or-name>', 'convert WinGet package into TXA manifests', 'chuy\u1ec3n g\u00f3i WinGet sang b\u1ed9 th\u1ebb manifest TXA'),
    @('txacli scan', 'list installed PC apps available on WinGet', 'li\u1ec7t k\u00ea ph\u1ea7n m\u1ec1m tr\u00ean m\u00e1y c\u00f3 s\u1eb5n tr\u00ean WinGet'),
    @('txacli -i [-y]', 'scan PC & import missing apps into TXA', 'qu\u00e9t m\u00e1y v\u00e0 import t\u1ef1 \u0111\u1ed9ng v\u00e0o kho TXA'),
    @('txacli build-api [-r <repo>] [-o <dir>]', 'build static txa.v1 REST API from manifests/', 't\u1ea1o t\u0129nh REST API txa.v1 t\u1eeb th\u01b0 m\u1ee5c manifests/'),
    @('txacli submit <folder|repo|api>', 'open PR(s) for manifest folder, repo, or API', 'm\u1edf Pull Request cho th\u01b0 m\u1ee5c g\u00f3i, kho ho\u1eb7c API')
)

Write-Heading (T 'hCreate')
Write-Table @(
    @('txacreate new <https-installer-url>', 'analyse + validate, then fork and open a PR', 'ph\u00e2n t\u00edch, ki\u1ec3m tra r\u1ed3i fork v\u00e0 m\u1edf Pull Request'),
    @('txacreate new "GitHub CLI"', 'auto-create release from app name or WinGet ID', 't\u1ef1 \u0111\u1ed9ng t\u1ea1o g\u00f3i t\u1eeb t\u00ean ph\u1ea7n m\u1ec1m ho\u1eb7c WinGet ID'),
    @('txacreate new -i', 'scan installed PC apps & create missing packages', 'qu\u00e9t ph\u1ea7n m\u1ec1m tr\u00ean m\u00e1y v\u00e0 t\u1ea1o g\u00f3i c\u00f2n thi\u1ebfu'),
    @('txacreate update TXAVL.HelloTool <url>', 'new version of an existing package', 'phi\u00ean b\u1ea3n m\u1edbi c\u1ee7a g\u00f3i \u0111\u00e3 c\u00f3'),
    @('txacreate submit <folder|repo|api>', 'open PR for release folder, repo root, or API', 'm\u1edf Pull Request cho th\u01b0 m\u1ee5c g\u00f3i, kho ho\u1eb7c API'),
    @('txacreate new <url> --dry-run', 'preview the YAML only, send nothing', 'ch\u1ec9 xem tr\u01b0\u1edbc YAML, kh\u00f4ng g\u1eedi g\u00ec'),
    @('txacreate new <url> --check', 'also run all 14 bot checks locally (slower)', 'ch\u1ea1y lu\u00f4n 14 b\u01b0\u1edbc ki\u1ec3m tra c\u1ee7a bot tr\u00ean m\u00e1y (ch\u1eadm h\u01a1n)'),
    @('txacreate hash setup.exe', 'SHA-256, engine and architecture', 'SHA-256, lo\u1ea1i b\u1ed9 c\u00e0i v\u00e0 ki\u1ebfn tr\u00fac'),
    @('txacreate validate <folder|repo>', 'run the bot checks locally', 'ch\u1ea1y c\u00e1c b\u01b0\u1edbc ki\u1ec3m tra c\u1ee7a bot tr\u00ean m\u00e1y'),
    @('txacreate token [--store|--clear]', 'optional: show, pre-authorize or forget GitHub login', 'tu\u1ef3 ch\u1ecdn: xem, c\u1ea5p tr\u01b0\u1edbc ho\u1eb7c qu\u00ean \u0111\u0103ng nh\u1eadp GitHub')
)
Write-Host (T 'noLogin') -ForegroundColor DarkGray

Write-Heading (T 'hEx')
Write-Host '  txapm search editor'
Write-Host '  txapm install TXAVL.NotepadPlusPlus'
Write-Host ('  txapm install ffmpeg          ' + (T 'portable'))
Write-Host ('  txapm install npm             ' + (T 'npmNote'))
Write-Host '  txapm upgrade --all'
Write-Host '  txacreate new https://vendor.example/app-2.1.0-x64.exe'
Write-Host ''
Write-Host (T 'help' $Repo) -ForegroundColor DarkGray
Write-Host ''
