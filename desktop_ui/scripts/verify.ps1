param([switch]$BuildFirmware)
. (Join-Path $PSScriptRoot 'common.ps1')
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$receipt = Join-Path $EvidenceRoot 'software_verified.json'
Push-Location $ProjectRoot
Start-Transcript -Path (Join-Path $EvidenceRoot ($stamp + '_verify.log'))
try {
    Assert-Python
    $initialHashes = Get-UiHashes
    & $PythonExe -I -X utf8 -m unittest discover -s (Join-Path $UiRoot 'tests') -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'UI protocol / service ownership tests failed. Smoke and build skipped.' }
    & $PythonExe -I -X utf8 (Join-Path $UiRoot 'app.py') --project-root $ProjectRoot --smoke-test
    if ($LASTEXITCODE -ne 0) { throw 'Visible source window startup / zoom / exit smoke failed.' }
    $pioState = 'NOT_RUN_IN_THIS_UI_STAGE; coordinate with volume window'
    if ($BuildFirmware) {
        if (-not (Test-Path -LiteralPath $PioPython)) { throw "Missing verified PIO Python: $PioPython" }
        & $PioPython -I -X utf8 -m platformio run
        if ($LASTEXITCODE -ne 0) { throw 'PlatformIO build failed. No upload performed.' }
        $pioState = 'BUILD_PASSED_NOT_UPLOADED'
    }
    $finalHashes = Get-UiHashes
    if (($initialHashes | ConvertTo-Json -Compress) -ne ($finalHashes | ConvertTo-Json -Compress)) { throw 'Source changed during verification. No new PASS receipt written.' }
    [ordered]@{ at = (Get-Date -Format o); status = 'OFFLINE_TESTS_AND_VISIBLE_SOURCE_SMOKE_PASSED'; hashes = $finalHashes; platformio = $pioState; hardware = 'NOT_TESTED'; live_service = 'NOT_TESTED'; screenshots = 'NOT_CAPTURED'; chinese_and_windows_dpi = 'NEEDS_HUMAN_VISUAL_CHECK' } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receipt -Encoding UTF8
    Write-Host "PASS: offline tests and visible source window. Live service, hardware and human visual acceptance are NOT verified. Evidence: $receipt"
}
finally { Stop-Transcript; Pop-Location }
