$ErrorActionPreference = 'Stop'
$UiRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ProjectRoot = (Resolve-Path (Join-Path $UiRoot '..')).Path
$PythonExe = 'C:\Users\ASUS\scoop\apps\python313\current\python.exe'
$PioPython = 'C:\Users\ASUS\.platformio\penv\Scripts\python.exe'
$EvidenceRoot = Join-Path $ProjectRoot '.pio\desktop_ui'
$TargetExe = Join-Path $ProjectRoot 'dist\PRPCompanion\PRPCompanion.exe'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Assert-Python {
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw "Missing verified Python: $PythonExe" }
    & $PythonExe -I -X utf8 -c "import sys, tkinter, serial, PyInstaller; assert sys.version_info[:2] == (3, 13); print('Python:', sys.version); print('Tk:', tkinter.TkVersion, 'pyserial:', serial.__version__, 'PyInstaller:', PyInstaller.__version__)"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 / Tk / pyserial / PyInstaller dependency check failed; nothing installed automatically.' }
}

function Get-UiHashes {
    $result = [ordered]@{}
    Get-ChildItem -LiteralPath $UiRoot -Recurse -File | Where-Object { $_.Extension -in @('.py', '.ps1') } | Sort-Object FullName | ForEach-Object {
        $relative = $_.FullName.Substring($ProjectRoot.Length + 1)
        $result[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    }
    foreach ($relative in @('server\launcher_app.py', 'server\launcher_console.py', 'server\launcher_core.py', 'server\services\bridge_identity.py', 'server\services\__init__.py', 'tools\build_launcher.ps1')) {
        $result[$relative] = (Get-FileHash -LiteralPath (Join-Path $ProjectRoot $relative) -Algorithm SHA256).Hash
    }
    return $result
}

function Assert-CompanionReplaceable {
    $instances = @(Get-CimInstance Win32_Process -Filter "Name = 'PRPCompanion.exe'" -ErrorAction Stop)
    $owners = @($instances | Where-Object { $_.ExecutablePath -and [string]::Equals($_.ExecutablePath, $TargetExe, [StringComparison]::OrdinalIgnoreCase) })
    if ($owners.Count -gt 0) {
        throw "Target PRPCompanion is running. PID: $(($owners | ForEach-Object { $_.ProcessId }) -join ', '). Close this app first. No process will be killed. Target: $TargetExe"
    }
    if (@($instances | Where-Object { -not $_.ExecutablePath }).Count -gt 0) { throw 'Cannot identify the full path of a PRPCompanion process. Check it in Task Manager before retrying.' }
    if (Test-Path -LiteralPath $TargetExe) {
        $item = Get-Item -LiteralPath $TargetExe
        if ($item.PSIsContainer -or $item.IsReadOnly) { throw "Target is a directory or read-only: $TargetExe" }
        $handle = $null
        try { $handle = [IO.File]::Open($TargetExe, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None) }
        catch { throw "Cannot exclusively open target for read/write. No deletion or permission changes performed. Target: $TargetExe. Reason: $($_.Exception.Message)" }
        finally { if ($null -ne $handle) { $handle.Dispose() } }
    }
}
