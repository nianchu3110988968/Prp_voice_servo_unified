param([switch]$SmokeTest, [switch]$Packaged)
. (Join-Path $PSScriptRoot 'common.ps1')
Push-Location $ProjectRoot
try {
    if ($Packaged) {
        if (-not (Test-Path -LiteralPath $TargetExe -PathType Leaf)) { throw "Independent EXE has not been built: $TargetExe" }
        $arguments = @('--project-root', ('"' + $ProjectRoot + '"'))
        if ($SmokeTest) { $arguments += '--smoke-test' }
        # User explicitly requested this visible interactive GUI.
        $process = Start-Process -FilePath $TargetExe -ArgumentList $arguments -PassThru -Wait
        if ($process.ExitCode -ne 0) { throw "PRPCompanion failed with exit code $($process.ExitCode)" }
    }
    else {
        Assert-Python
        $arguments = @('-I', '-X', 'utf8', (Join-Path $UiRoot 'app.py'), '--project-root', $ProjectRoot)
        if ($SmokeTest) { $arguments += '--smoke-test' }
        & $PythonExe @arguments
        if ($LASTEXITCODE -ne 0) { throw "PRPCompanion source failed: $LASTEXITCODE" }
    }
}
finally { Pop-Location }
