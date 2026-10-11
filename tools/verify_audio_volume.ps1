# Visible VS Code PowerShell only. Offline tests and one build; no upload/serial/services.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pioPython = 'C:\Users\ASUS\.platformio\penv\Scripts\python.exe'
$git = 'C:\Users\ASUS\scoop\apps\git\current\cmd\git.exe'
$hostBuild = Join-Path $projectRoot '.pio\volume_control'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
New-Item -ItemType Directory -Path $hostBuild -Force | Out-Null
$transcript = Join-Path $hostBuild "verify_$stamp.log"
$transcriptStarted = $false
$oldEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$owned = @('main/main.cc','main/bsp_board.cc','main/bsp_board.h','main/audio_volume.h',
    'main/audio_volume_protocol.h','tests/firmware/audio_volume_test.cc',
    'tests/firmware/audio_volume_bsp_test.cc','tests/audio_volume_stubs',
    'tools/verify_audio_volume.ps1','docs/项目指南/audio_volume_protocol.md')

function Get-SourceHashes {
    $hashes = @{}
    $files = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'main') -Recurse -File)
    $files += @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'tests') -Recurse -File)
    foreach ($relative in @('platformio.ini','CMakeLists.txt','partitions.csv','sdkconfig.defaults',
            'sdkconfig.defaults.esp32s3','sdkconfig.esp32-s3-devkitc-1',
            'tools/verify_audio_volume.ps1','tools/verify_phrase_cache.ps1')) {
        $files += Get-Item -LiteralPath (Join-Path $projectRoot $relative)
    }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($projectRoot.Length + 1).Replace('\','/')
        $hashes[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    }
    return $hashes
}
function Assert-SameSources($before) {
    $after = Get-SourceHashes
    if ($before.Count -ne $after.Count) { throw 'Source inventory changed during validation.' }
    foreach ($key in $before.Keys) {
        if ($before[$key] -ne $after[$key]) { throw "Source changed during validation: $key" }
    }
}
Push-Location $projectRoot
try {
    Start-Transcript -Path $transcript | Out-Null
    $transcriptStarted = $true
    Write-Host "Shell: $($PSVersionTable.PSVersion); project: $projectRoot"
    foreach ($tool in @($pioPython, $git)) {
        if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Required tool missing: $tool" }
    }
    # Do not print complete process command lines (they may contain unrelated data).
    $builders = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -match '(?i)(-m\s+platformio|platformio(?:\.exe)?["\s]).*\brun\b'
    })
    if ($builders.Count) { throw "Another PlatformIO run may be active; coordinate first. PID: $($builders.ProcessId -join ',')" }
    & $git --version
    if ($LASTEXITCODE -ne 0) { throw 'Git unavailable.' }
    & $git status --short
    if ($LASTEXITCODE -ne 0) { throw 'Git status failed.' }
    & $git diff --check -- @owned
    if ($LASTEXITCODE -ne 0) { throw 'Owned-file diff check failed.' }
    & $git diff --stat -- @owned
    if ($LASTEXITCODE -ne 0) { throw 'Owned-file diff summary failed.' }
    $sources = Get-SourceHashes
    $backupDir = Join-Path $hostBuild 'before_20261012'
    $backup = Get-Content -LiteralPath (Join-Path $backupDir 'rollback_manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($backup.files.'firmware.bin'.sha256 -ne 'd82c168982703c5f168d129c82d6898e45c49e1b25dccb0b15a2db15e1202b67') {
        throw 'Unexpected rollback baseline; do not overwrite the build.'
    }
    foreach ($file in $backup.files.PSObject.Properties) {
        if ((Get-FileHash -LiteralPath (Join-Path $backupDir $file.Name) -Algorithm SHA256).Hash -ne $file.Value.sha256) {
            throw "Rollback backup mismatch: $($file.Name)"
        }
    }
    Write-Host '[1/3] PCM16 volume, protocol, atomic and playback gate host checks'
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        $vsWhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
        if (-not (Test-Path -LiteralPath $vsWhere)) { throw 'MSVC discovery tool missing.' }
        $vsRoot = & $vsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -ne 0) { throw 'MSVC discovery failed.' }
        if (-not $vsRoot) { throw 'MSVC C++ toolchain missing.' }
        Import-Module (Join-Path $vsRoot 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
        Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
    }
    $exe = Join-Path $hostBuild 'audio_volume_test.exe'
    $obj = Join-Path $hostBuild 'audio_volume_test.obj'
    & cl.exe /nologo /EHsc /std:c++17 /utf-8 /UNDEBUG /Itests/firmware_stubs tests/firmware/audio_volume_test.cc "/Fo$obj" "/Fe$exe"
    if ($LASTEXITCODE -ne 0) { throw 'Volume host compilation failed; stop before firmware build.' }
    & $exe
    if ($LASTEXITCODE -ne 0) { throw 'Volume host checks failed; stop before firmware build.' }
    $bspExe = Join-Path $hostBuild 'audio_volume_bsp_test.exe'
    $bspObj = Join-Path $hostBuild 'audio_volume_bsp_test.obj'
    & cl.exe /nologo /EHsc /std:c++20 /utf-8 /UNDEBUG /Itests/audio_volume_stubs /Itests/firmware_stubs tests/firmware/audio_volume_bsp_test.cc "/Fo$bspObj" "/Fe$bspExe"
    if ($LASTEXITCODE -ne 0) { throw 'BSP volume host compilation failed; stop before firmware build.' }
    & $bspExe
    if ($LASTEXITCODE -ne 0) { throw 'BSP volume host checks failed; stop before firmware build.' }
    Write-Host '[2/3] Existing download/cache/start callback regression (offline)'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify_phrase_cache.ps1') -AudioOnly
    if ($LASTEXITCODE -ne 0) { throw 'Existing audio regression failed; stop before firmware build.' }
    Assert-SameSources $sources
    Write-Host '[3/3] Dedicated PlatformIO Core 6.2.0; build only'
    $core = & $pioPython -I -X utf8 -m platformio --version
    if ($LASTEXITCODE -ne 0) { throw 'Dedicated PlatformIO startup failed.' }
    Write-Host ($core -join "`n")
    if (($core -join ' ') -notmatch '\b6\.2\.0\b') { throw 'Unexpected PlatformIO Core; recheck before building.' }
    & $pioPython -I -X utf8 -m platformio run -e esp32-s3-devkitc-1
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed; do not flash.' }
    Assert-SameSources $sources
    $firmware = Join-Path $projectRoot '.pio\build\esp32-s3-devkitc-1\firmware.bin'
    $version = '2026-10-12-volume-v1'
    if (-not [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($firmware)).Contains($version)) {
        throw 'Built image lacks the expected volume version.'
    }
    $result = [ordered]@{
        result='PASS'; scope='volume-and-existing-audio-host-tests-plus-build'
        firmware_version=$version; firmware_sha256=(Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash
        source_sha256=$sources; transcript=$transcript; rollback_manifest=(Join-Path $backupDir 'rollback_manifest.json')
        flashed=$false; board_version_observed=$false; hardware_tested=$false
    }
    $evidence = Join-Path $hostBuild "result_$stamp.json"
    $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidence -Encoding UTF8
    Write-Host "PASS: software checks and firmware build only. Evidence: $evidence"
    Write-Host 'No upload, serial access, service changes or Git commit/push performed.'
}
finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    [Console]::OutputEncoding = $oldEncoding
    Pop-Location
    Write-Host "Verification transcript: $transcript"
}
