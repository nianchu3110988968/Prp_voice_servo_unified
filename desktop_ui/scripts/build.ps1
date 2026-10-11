. (Join-Path $PSScriptRoot 'common.ps1')
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
Push-Location $ProjectRoot
Start-Transcript -Path (Join-Path $EvidenceRoot ((Get-Date -Format 'yyyyMMdd_HHmmss') + '_build.log'))
try {
    Assert-CompanionReplaceable
    Assert-Python
    $receiptPath = Join-Path $EvidenceRoot 'software_verified.json'
    if (-not (Test-Path -LiteralPath $receiptPath)) { throw 'Run verify.ps1 successfully in the visible terminal before packaging.' }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($receipt.status -ne 'OFFLINE_TESTS_AND_VISIBLE_SOURCE_SMOKE_PASSED') { throw 'Invalid software verification receipt.' }
    $before = Get-UiHashes
    foreach ($key in $before.Keys) {
        if ($receipt.hashes.$key -ne $before[$key]) { throw "Source changed since verification: $key" }
    }
    Assert-CompanionReplaceable
    & $PythonExe -I -X utf8 -m PyInstaller --noconfirm --clean --onefile --windowed --name PRPCompanion --paths $ProjectRoot --paths (Join-Path $ProjectRoot 'server') --hidden-import serial.tools.list_ports_windows --distpath (Join-Path $ProjectRoot 'dist\PRPCompanion') --workpath (Join-Path $ProjectRoot 'build\companion') --specpath (Join-Path $ProjectRoot 'build\companion') (Join-Path $UiRoot 'app.py')
    if ($LASTEXITCODE -ne 0) { throw 'Independent package failed; no later checks executed. Target may have become occupied after preflight. Original PRPLauncher is untouched.' }
    $after = Get-UiHashes
    if (($before | ConvertTo-Json -Compress) -ne ($after | ConvertTo-Json -Compress)) { throw 'Source changed during packaging; package is NOT verified.' }
    if (-not (Test-Path -LiteralPath $TargetExe -PathType Leaf)) { throw 'PyInstaller returned without the expected independent EXE.' }
    # Deliberately visible offline GUI requested for package verification.
    $process = Start-Process -FilePath $TargetExe -ArgumentList @('--project-root', ('"' + $ProjectRoot + '"'), '--smoke-test') -PassThru
    if (-not $process.WaitForExit(30000)) { throw 'Visible EXE did not exit in 30 seconds. Inspect its window; no automatic kill.' }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Packaged GUI smoke failed: $($process.ExitCode)" }
    [ordered]@{ at = (Get-Date -Format o); status = 'PACKAGE_AND_VISIBLE_OFFLINE_SMOKE_PASSED'; exe = $TargetExe; sha256 = (Get-FileHash -LiteralPath $TargetExe -Algorithm SHA256).Hash; source_hashes = $after; real_service_and_device = 'NOT_VERIFIED_BY_BUILD' } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $EvidenceRoot 'package_verified.json') -Encoding UTF8
    Write-Host "PASS: independent EXE built and visible offline smoke passed. Hardware remains unverified: $TargetExe"
}
finally { Stop-Transcript; Pop-Location }
