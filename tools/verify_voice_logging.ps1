# Run manually from a visible VS Code PowerShell terminal. No servers or flashing.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    Write-Host '[1/3] Offline server tests (no real models, no service requests)'
    & python -X utf8 -m unittest discover -s server/tests -p test_latency_trace.py -v
    if ($LASTEXITCODE -ne 0) { throw 'Server log tests failed; stop before firmware build.' }

    Write-Host '[2/3] platformio run (build only; no upload)'
    # Use VS Code's dedicated Core, not a different pip-installed Core on PATH.
    # Mixing Cores can replace the shared tool-scons package during a build.
    $pioPython = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.platformio\penv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pioPython -PathType Leaf)) {
        throw "Dedicated PlatformIO Python not found: $pioPython. Repair the VS Code PlatformIO environment; no PATH fallback was used."
    }
    Write-Host "[PlatformIO] Python: $pioPython"
    # Isolated mode ignores external PYTHONPATH and user-site packages.
    & $pioPython -I -X utf8 -m platformio --version
    if ($LASTEXITCODE -ne 0) { throw 'Dedicated PlatformIO Core could not start; no PATH fallback was used.' }
    & $pioPython -I -X utf8 -m platformio run
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed; do not flash.' }

    Write-Host '[3/3] Native observer regression test (MSVC)'
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        $vsWhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
        if (-not (Test-Path -LiteralPath $vsWhere)) { throw 'MSVC not found; host tests NOT run.' }
        $vsRoot = & $vsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if (-not $vsRoot) { throw 'MSVC C++ toolchain not found; host tests NOT run.' }
        Import-Module (Join-Path $vsRoot 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
        Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
    }
    $hostBuild = Join-Path $projectRoot '.pio\voice_log_host'
    New-Item -ItemType Directory -Path $hostBuild -Force | Out-Null
    $hostExe = Join-Path $hostBuild 'voice_trace_test.exe'
    $hostObj = Join-Path $hostBuild 'voice_trace_test.obj'
    & cl.exe /nologo /EHsc /std:c++17 /utf-8 /UNDEBUG /Itests/firmware_stubs tests/firmware/voice_trace_test.cc "/Fo$hostObj" "/Fe$hostExe"
    if ($LASTEXITCODE -ne 0) { throw 'Host test build failed.' }
    & $hostExe
    if ($LASTEXITCODE -ne 0) { throw 'Host observer regression failed.' }
    Write-Host 'PASS: all three checks passed. No firmware was flashed; no services were restarted.'
}
finally {
    Pop-Location
}
