# Run only in the user's visible VS Code PowerShell. No serial, service starts or upload.
[CmdletBinding()]
param([switch]$HostOnly, [string]$Python = 'C:\Users\ASUS\scoop\apps\python313\current\python.exe')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$hostBuild = Join-Path $projectRoot '.pio\servo_channels_host'
New-Item -ItemType Directory -Path $hostBuild -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$transcriptPath = Join-Path $hostBuild ("verify_$stamp.log")
$transcriptStarted = $false
$checkedSources = @('main/main.cc', 'main/robot_motions.cc', 'main/robot_motions.h',
    'main/robot_config.h', 'main/pca9685_controller.cc', 'main/audio_reply_player.cc',
    'main/audio_playback_gate.h', 'main/bsp_board.cc', 'server/services/motion_policy.py',
    'server/configs/motion_catalog.json', 'server/services/phrase_library.py',
    'server/services/dialogue_service.py', 'server/tests/test_phrase_acknowledge.py',
    'tests/firmware/servo_channels_test.cc', 'tools/verify_servo_channels.ps1',
    'tools/verify_phrase_cache.ps1', 'tools/verify_voice_logging.ps1')
$sourceHashes = @{}
foreach ($relative in $checkedSources) {
    $sourceHashes[$relative] = (Get-FileHash -LiteralPath (Join-Path $projectRoot $relative) -Algorithm SHA256).Hash
}
Push-Location $projectRoot
try {
    Start-Transcript -Path $transcriptPath | Out-Null
    $transcriptStarted = $true
    if (-not $HostOnly) {
        # Existing offline voice/phrase tests, platformio run, and audio/trace host tests.
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify_phrase_cache.ps1') -Python $Python
        if ($LASTEXITCODE -ne 0) { throw 'Voice/phrase/build verification failed; stop before servo host tests.' }
    }
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        $vsWhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
        if (-not (Test-Path -LiteralPath $vsWhere)) { throw 'MSVC not found; servo tests NOT run.' }
        $vsRoot = & $vsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -ne 0) { throw 'MSVC discovery failed.' }
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
    foreach ($relative in $checkedSources) {
        $after = (Get-FileHash -LiteralPath (Join-Path $projectRoot $relative) -Algorithm SHA256).Hash
        if ($after -ne $sourceHashes[$relative]) { throw "Source changed during validation: $relative. Do not claim this result for the new source." }
    }
    if (-not $HostOnly) {
        $firmware = Join-Path $projectRoot '.pio\build\esp32-s3-devkitc-1\firmware.bin'
        $sourceText = Get-Content -LiteralPath (Join-Path $projectRoot 'main\main.cc') -Raw -Encoding UTF8
        $version = [regex]::Match($sourceText, 'FIRMWARE_VERSION\s*=\s*"([^"]+)"').Groups[1].Value
        $imageText = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($firmware))
        if (-not $version -or -not $imageText.Contains($version)) { throw 'Built image does not contain the source firmware version.' }
        $evidence = [ordered]@{
            result = 'PASS'; scope = 'offline-tests-and-build-only'; firmware_version = $version
            firmware_sha256 = (Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash
            source_sha256 = $sourceHashes; transcript = $transcriptPath
            flashed = $false; hardware_tested = $false
        }
        $evidencePath = Join-Path $hostBuild ("result_$stamp.json")
        $evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $evidencePath -Encoding UTF8
        Write-Host "Evidence: $evidencePath"
    }
    if ($HostOnly) { Write-Host 'PASS: servo host tests only. Firmware build NOT rerun. No flashing or services.' }
    else { Write-Host 'PASS: voice/phrase tests, platformio run, and servo host tests. No flashing or services.' }
}
finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    Write-Host "Full verification log: $transcriptPath"
    Pop-Location
}
