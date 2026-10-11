# Run in the user's visible VS Code PowerShell after explicit flashing approval.
# External servo 5V must be disconnected; ESP32 remains powered by USB.
[CmdletBinding()]
param([string]$Port, [string]$EvidencePath)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pioPython = 'C:\Users\ASUS\.platformio\penv\Scripts\python.exe'
if (-not $EvidencePath) {
    $EvidencePath = Join-Path $projectRoot '.pio\servo_channels_host\result_20261011_221929.json'
}
$firmware = Join-Path $projectRoot '.pio\build\esp32-s3-devkitc-1\firmware.bin'
$logDir = Join-Path $projectRoot '.pio\servo_channels_host'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logPath = Join-Path $logDir ("upload_$stamp.log")
$transcriptStarted = $false
Push-Location $projectRoot
try {
    Start-Transcript -Path $logPath | Out-Null
    $transcriptStarted = $true
    if (-not (Test-Path -LiteralPath $pioPython -PathType Leaf)) { throw 'Dedicated PlatformIO Python missing.' }
    $evidence = Get-Content -LiteralPath $EvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($evidence.result -ne 'PASS' -or $evidence.firmware_version -ne '2026-10-11-rl-ack-v1') {
        throw 'Expected passing rl-ack-v1 build evidence. Nothing uploaded.'
    }
    $hash = (Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash
    if ($hash -ne $evidence.firmware_sha256) { throw 'Firmware differs from the verified image. Nothing uploaded.' }
    if (-not $evidence.source_sha256 -or @($evidence.source_sha256.PSObject.Properties).Count -eq 0) {
        throw 'Source evidence missing. Nothing uploaded.'
    }
    foreach ($source in $evidence.source_sha256.PSObject.Properties) {
        $actual = (Get-FileHash -LiteralPath (Join-Path $projectRoot $source.Name) -Algorithm SHA256).Hash
        if ($actual -ne $source.Value) { throw "Source changed since validation: $($source.Name). Nothing uploaded." }
    }
    & $pioPython -I -X utf8 -m platformio --version
    if ($LASTEXITCODE -ne 0) { throw 'PlatformIO startup failed.' }
    $portJson = & $pioPython -I -X utf8 -m platformio device list --json-output
    if ($LASTEXITCODE -ne 0) { throw 'Serial port enumeration failed.' }
    $ports = @((($portJson -join "`n") | ConvertFrom-Json) | Where-Object { $_.port -match '^COM[0-9]+$' })
    if ($ports.Count -eq 0) { throw 'No serial ports found. Keep USB connected and check the driver.' }
    $ports | Select-Object port, description, hwid | Format-Table -AutoSize | Out-Host
    if (-not $Port) { $Port = Read-Host 'Enter the current ESP32 COM port from the list (no default)' }
    $Port = $Port.Trim().ToUpperInvariant()
    if ($Port -notmatch '^COM[0-9]+$' -or $Port -notin @($ports | ForEach-Object { $_.port })) {
        throw 'Selected port is not in the current list. Nothing uploaded.'
    }
    Write-Host "Uploading verified $($evidence.firmware_version) to $Port"
    Write-Host "Firmware SHA256: $hash"
    Write-Host 'No rebuild, service restart, serial monitor or motion command.'
    & $pioPython -I -X utf8 -m platformio run -e esp32-s3-devkitc-1 -t nobuild -t upload --upload-port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Upload failed. No automatic retry; preserve this log.' }
    if ((Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash -ne $hash) {
        throw 'Image changed during upload. Do not claim the intended version was flashed; inspect the log.'
    }
    [ordered]@{
        upload_exit_code = 0; port = $Port; firmware_version = $evidence.firmware_version
        firmware_sha256 = $hash; build_evidence = $EvidencePath; transcript = $logPath
        board_version_observed = $false; hardware_tested = $false
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDir ("upload_$stamp.json")) -Encoding UTF8
    Write-Host 'UPLOAD SUCCESS. Board version, PWM-off reply and local audio still require observation.'
}
finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    Write-Host "Upload log: $logPath"
    Pop-Location
}
