param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    & $Python -X utf8 -m unittest discover -s server/tests -p "test_*.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Server tests failed: $LASTEXITCODE" }
    & $Python -X utf8 server/launcher_app.py --smoke-test
    if ($LASTEXITCODE -ne 0) { throw "Launcher Tk smoke test failed" }
    $pioPython = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.platformio\penv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pioPython -PathType Leaf)) {
        throw "Dedicated PlatformIO Python not found: $pioPython; no PATH fallback was used."
    }
    Write-Host "[PlatformIO] Python: $pioPython"
    & $pioPython -I -X utf8 -m platformio --version
    if ($LASTEXITCODE -ne 0) { throw 'Dedicated PlatformIO Core could not start; no PATH fallback was used.' }
    & $pioPython -I -X utf8 -m platformio run
    if ($LASTEXITCODE -ne 0) { throw "platformio run failed: $LASTEXITCODE" }
    Write-Host "PASS: server tests + launcher Tk smoke + platformio run (no flash, no real services)"
}
finally { Pop-Location }
