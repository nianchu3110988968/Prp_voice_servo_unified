# Run only in the user's visible VS Code PowerShell. No serial, service starts or upload.
[CmdletBinding()]
param([switch]$HostOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$hostBuild = Join-Path $projectRoot '.pio\servo_channels_host'
New-Item -ItemType Directory -Path $hostBuild -Force | Out-Null
Push-Location $projectRoot
try {
    if (-not $HostOnly) {
        # Existing offline voice/phrase tests, platformio run, and audio/trace host tests.
        & (Join-Path $PSScriptRoot 'verify_phrase_cache.ps1')
    }
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        $vsWhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
        if (-not (Test-Path -LiteralPath $vsWhere)) { throw 'MSVC not found; servo tests NOT run.' }
        $vsRoot = & $vsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if (-not $vsRoot) { throw 'MSVC C++ toolchain not found; servo tests NOT run.' }
        Import-Module (Join-Path $vsRoot 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
        Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
    }
    Write-Host '[Servo] Real PCA9685 driver and motion task, simulated I2C/FreeRTOS only'
    $hostExe = Join-Path $hostBuild 'servo_channels_test.exe'
    Push-Location $hostBuild
    try {
        & cl.exe /nologo /EHsc /std:c++20 /utf-8 /UNDEBUG "/I$projectRoot\tests\servo_stubs" "/I$projectRoot\tests\firmware_stubs" `
            "$projectRoot\tests\firmware\servo_channels_test.cc" "$projectRoot\main\pca9685_controller.cc" "$projectRoot\main\robot_motions.cc" "/Fe$hostExe"
        if ($LASTEXITCODE -ne 0) { throw 'Servo host build failed; do not flash.' }
        & $hostExe
        if ($LASTEXITCODE -ne 0) { throw 'Servo host regression failed; do not flash.' }
    }
    finally { Pop-Location }
    if ($HostOnly) { Write-Host 'PASS: servo host tests only. Firmware build NOT rerun. No flashing or services.' }
    else { Write-Host 'PASS: voice/phrase tests, platformio run, and servo host tests. No flashing or services.' }
}
finally { Pop-Location }
