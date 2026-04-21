param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

$distExe = Join-Path $projectRoot "dist\AutomatedApply\AutomatedApply.exe"
$runningDistApp = Get-Process -Name "AutomatedApply" -ErrorAction SilentlyContinue | Where-Object {
    try {
        $_.Path -eq $distExe
    } catch {
        $false
    }
}
if ($runningDistApp) {
    $pids = ($runningDistApp | Select-Object -ExpandProperty Id) -join ", "
    throw "Feche o AutomatedApply.exe em execucao antes de reconstruir. PID(s): $pids"
}

$distChromeProfiles = @(
    (Join-Path $projectRoot "dist\AutomatedApply\google-chrome-control-profile"),
    (Join-Path $projectRoot "dist\AutomatedApply\playwright-profile")
)
$runningBotChrome = Get-CimInstance Win32_Process -Filter "name = 'chrome.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $commandLine = $_.CommandLine
    $distChromeProfiles | Where-Object { $commandLine -like "*$_*" }
}
if ($runningBotChrome) {
    $pids = ($runningBotChrome | Select-Object -ExpandProperty ProcessId) -join ", "
    throw "Feche o Chrome controlavel do bot antes de reconstruir. PID(s): $pids"
}

$runtimeBackup = $null
$existingRuntime = Join-Path $projectRoot "dist\AutomatedApply\data\runtime"
if (Test-Path -LiteralPath $existingRuntime) {
    $runtimeBackup = Join-Path ([System.IO.Path]::GetTempPath()) ("AutomatedApply-runtime-" + [guid]::NewGuid().ToString("N"))
    Copy-Item -LiteralPath $existingRuntime -Destination $runtimeBackup -Recurse
}

if ($Clean) {
    foreach ($path in @("build", "dist", "AutomatedApply.spec")) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
}

python -m pip install -e .
python -m pip install pyinstaller
python -m playwright install chromium

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name AutomatedApply `
    --collect-submodules playwright `
    --hidden-import yaml `
    --hidden-import greenlet `
    app/gui.py

$distApp = Join-Path $projectRoot "dist\AutomatedApply"
if (-not (Test-Path -LiteralPath $distApp)) {
    throw "Build falhou: pasta nao encontrada: $distApp"
}

foreach ($folder in @("data", "scripts")) {
    $source = Join-Path $projectRoot $folder
    $target = Join-Path $distApp $folder
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
    Copy-Item -LiteralPath $source -Destination $target -Recurse
}

$distRuntime = Join-Path $distApp "data\runtime"
if (Test-Path -LiteralPath $distRuntime) {
    Remove-Item -LiteralPath $distRuntime -Recurse -Force
}
New-Item -ItemType Directory -Path $distRuntime | Out-Null
if ($runtimeBackup -and (Test-Path -LiteralPath $runtimeBackup)) {
    Copy-Item -Path (Join-Path $runtimeBackup "*") -Destination $distRuntime -Recurse -Force
    Remove-Item -LiteralPath $runtimeBackup -Recurse -Force
}

$playwrightBrowsers = Join-Path $env:LOCALAPPDATA "ms-playwright"
if (Test-Path -LiteralPath $playwrightBrowsers) {
    $targetBrowsers = Join-Path $distApp "ms-playwright"
    if (Test-Path -LiteralPath $targetBrowsers) {
        Remove-Item -LiteralPath $targetBrowsers -Recurse -Force
    }
    Copy-Item -LiteralPath $playwrightBrowsers -Destination $targetBrowsers -Recurse
} else {
    Write-Host "Aviso: pasta ms-playwright nao encontrada em $playwrightBrowsers" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Build concluido:" -ForegroundColor Green
Write-Host (Join-Path $distApp "AutomatedApply.exe")
Write-Host ""
Write-Host "Chromium do Playwright copiado para:" -ForegroundColor Green
Write-Host (Join-Path $distApp "ms-playwright")
