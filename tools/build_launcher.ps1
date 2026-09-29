$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $projectRoot
try {
    & python -c "import serial; import serial.tools.list_ports"
    if ($LASTEXITCODE -ne 0) { throw "Install serial support: python -m pip install pyserial" }
    & python -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) { throw "Install PyInstaller in this visible terminal: python -m pip install pyinstaller" }
    & python -m PyInstaller --noconfirm --clean --onefile --windowed --name PRPLauncher --paths server --hidden-import serial.tools.list_ports_windows --distpath dist --workpath build/launcher --specpath build server/launcher_app.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
    $exe = Join-Path $projectRoot "dist/PRPLauncher.exe"
    # This explicitly visible real Tk smoke test starts no services.
    $process = Start-Process -FilePath $exe -ArgumentList @("--project-root", ('"' + $projectRoot + '"'), "--smoke-test") -PassThru
    if (-not $process.WaitForExit(30000)) { throw "EXE did not exit in 30s; inspect its visible window" }
    if ($process.ExitCode -ne 0) { throw "EXE startup/exit check failed: $($process.ExitCode)" }
    Write-Host "PASS: package built and Tk window startup/exit succeeded; real service integration not verified"
}
finally { Pop-Location }
