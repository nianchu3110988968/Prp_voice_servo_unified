$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    & python -X utf8 -m unittest discover -s server/tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Server tests failed: $LASTEXITCODE" }
    & platformio run
    if ($LASTEXITCODE -ne 0) { throw "platformio run failed: $LASTEXITCODE" }
    Write-Host "PASS: server tests + platformio run (no flash, no real services)"
}
finally { Pop-Location }
