# Visible VS Code terminal only. Offline, build-only, no upload or service restart.
[CmdletBinding()]
param([switch]$AudioOnly, [switch]$OutputCheck)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$hostBuild = Join-Path $projectRoot '.pio\phrase_cache_host'
New-Item -ItemType Directory -Path $hostBuild -Force | Out-Null
$transcriptPath = Join-Path $hostBuild ('verify_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')
$transcriptStarted = $false
$previousOutputEncoding = [Console]::OutputEncoding
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
function ConvertTo-NativeArgument {
    param([string]$Value)
    # Windows CRT argument quoting. No shell evaluates these arguments.
    $escaped = [regex]::Replace($Value, '(\\*)"', {
        param($match)
        ('\' * (2 * $match.Groups[1].Length + 1)) + '"'
    })
    $escaped = [regex]::Replace($escaped, '(\\+)$', {
        param($match)
        $match.Value + $match.Value
    })
    return '"' + $escaped + '"'
}
function Invoke-VisibleNative {
    param([string]$Program, [string[]]$NativeArguments, [string]$FailureMessage)
    # Read both byte streams as UTF-8, then display them in this VS Code terminal.
    # PS5's 2>&1 produces NativeCommandError objects for successful unittest output.
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $resolvedCommand = Get-Command $Program -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $executablePath = [string]$resolvedCommand.Path
    if (-not $executablePath -or -not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
        throw "Executable not found for $Program"
    }
    $startInfo.FileName = $executablePath
    $startInfo.Arguments = (($NativeArguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ')
    $startInfo.WorkingDirectory = $projectRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = $utf8
    $startInfo.StandardErrorEncoding = $utf8
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $started = $false
    try {
        try { $started = $process.Start() }
        catch { throw "Could not start '$executablePath' in '$projectRoot': $($_.Exception.Message)" }
        if (-not $started) { throw "Could not start $Program" }
        $stdoutRead = $process.StandardOutput.ReadLineAsync()
        $stderrRead = $process.StandardError.ReadLineAsync()
        while ($null -ne $stdoutRead -or $null -ne $stderrRead) {
            if ($null -ne $stdoutRead -and $stdoutRead.IsCompleted) {
                $line = $stdoutRead.GetAwaiter().GetResult()
                if ($null -eq $line) { $stdoutRead = $null }
                else { Write-Host $line; $stdoutRead = $process.StandardOutput.ReadLineAsync() }
            }
            if ($null -ne $stderrRead -and $stderrRead.IsCompleted) {
                $line = $stderrRead.GetAwaiter().GetResult()
                if ($null -eq $line) { $stderrRead = $null }
                else { Write-Host $line; $stderrRead = $process.StandardError.ReadLineAsync() }
            }
            if ($null -ne $stdoutRead -or $null -ne $stderrRead) { Start-Sleep -Milliseconds 10 }
        }
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) { throw "$FailureMessage (exit=$($process.ExitCode))" }
    }
    finally {
        # Only this invocation's child is stopped on cancellation; no server PIDs.
        if ($started -and -not $process.HasExited) { $process.Kill() }
        $process.Dispose()
    }
}
Push-Location $projectRoot
try {
    Start-Transcript -Path $transcriptPath | Out-Null
    $transcriptStarted = $true
    if ($OutputCheck) {
        # ASCII source with Unicode escapes also works when PS5 reads this .ps1
        # without a BOM. The child emits actual Chinese UTF-8 on both streams.
        Invoke-VisibleNative 'python' @('-X', 'utf8', '-c', 'import sys; print("\u4e2d\u6587\u6807\u51c6\u8f93\u51fa\uff1a\u4f60\u597d"); print("\u4e2d\u6587\u6807\u51c6\u9519\u8bef\uff1a\u6d4b\u8bd5\u901a\u8fc7", file=sys.stderr)') 'Output check failed.'
        try {
            Invoke-VisibleNative 'python' @('-c', 'import sys; sys.exit(3)') 'Expected exit-code probe'
            throw 'Nonzero exit code was not detected.'
        }
        catch {
            if ($_.Exception.Message -ne 'Expected exit-code probe (exit=3)') { throw }
        }
        Write-Host 'PASS: UTF-8 stdout/stderr and nonzero exit-code handling. No build, models, servers or flashing.'
        return
    }
    if (-not $AudioOnly) {
        Write-Host '[1/3] Offline phrase library/pipeline/job tests (fake models only)'
        Invoke-VisibleNative 'python' @('-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'server/tests', '-p', 'test_phrase_library.py', '-v') 'Phrase library tests failed.'
        Write-Host '[2/3] Existing logging tests + platformio run + observer host tests'
        & (Join-Path $PSScriptRoot 'verify_voice_logging.ps1') | Out-Host
    }
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        $vsWhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
        if (-not (Test-Path -LiteralPath $vsWhere)) { throw 'MSVC not found; host tests NOT run.' }
        $vsRoot = & $vsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if (-not $vsRoot) { throw 'MSVC C++ toolchain not found; host tests NOT run.' }
        Import-Module (Join-Path $vsRoot 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
        Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
    }
    Write-Host '[3/3] Production audio download-only host regression'
    $hostExe = Join-Path $hostBuild 'audio_download_test.exe'
    $hostObj = Join-Path $hostBuild 'audio_download_test.obj'
    # C++20 supports designated initialization; /GF- must NOT mask URL pointer
    # arithmetic bugs by merging equal string literals. Keep this regression.
    Invoke-VisibleNative 'cl.exe' @('/nologo', '/EHsc', '/std:c++20', '/Od', '/GF-', '/utf-8', '/UNDEBUG', '/Itests/firmware_stubs', 'tests/firmware/audio_download_test.cc', "/Fo$hostObj", "/Fe$hostExe") 'Audio download host test build failed.'
    Invoke-VisibleNative $hostExe @() 'Audio download-only regression failed.'
    if ($AudioOnly) { Write-Host 'PASS: audio host check only (other checks not rerun). No firmware flashed; no services restarted.' }
    else { Write-Host 'PASS: phrase cache checks passed. No firmware flashed; no services restarted.' }
}
finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    Write-Host "Full verification log: $transcriptPath"
    [Console]::OutputEncoding = $previousOutputEncoding
    Pop-Location
}
