#requires -Version 7.0
param([switch]$Execute, [switch]$Resume)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
if ($projectRoot -ne 'E:\Projects2026\Prp_voice_servo_unified') {
    throw 'This one-time migration is restricted to the verified project root.'
}
$plan = @(
    @{ Source = 'E:\Projects2026\Prp'; Destination = (Join-Path $projectRoot 'legacy\Prp_servo_arduino') },
    @{ Source = ('E:\college\' + [string]::Concat([char[]]@(0x6bdb,0x7ed2,0x6cbb,0x6108,0x673a,0x5668,0x4eba)) + 'PRP');
       Destination = (Join-Path $projectRoot ('archive\PRP_' + [string]::Concat([char[]]@(0x539f,0x59cb,0x9879,0x76ee,0x8d44,0x6599)))) }
)
$auditDir = Join-Path $projectRoot '.local_migration\20260915'
$auditFile = Join-Path $auditDir 'files.json'
if ((Test-Path -LiteralPath $auditFile) -and !$Resume) { throw 'Migration audit already exists. Inspect it; use -Execute -Resume only for the approved migration.' }
$records = @()
if ($Resume) {
    if (!$Execute) { throw 'Resume requires Execute.' }
    $records = @(Get-Content -Raw -LiteralPath $auditFile | ConvertFrom-Json -AsHashtable)
    if ($records.Count -ne $plan.Count) { throw 'Unexpected audit target count.' }
    for ($i=0; $i -lt $plan.Count; $i++) {
        if ($records[$i].Source -ne $plan[$i].Source -or $records[$i].Destination -ne $plan[$i].Destination) {
            throw 'Audit targets do not match the hardcoded approved paths.'
        }
    }
} else {
foreach ($item in $plan) {
    $source = (Resolve-Path -LiteralPath $item.Source).Path.TrimEnd('\')
    $destination = [IO.Path]::GetFullPath($item.Destination)
    if ($source -ne $item.Source -or !$destination.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Resolved migration path escaped the approved scope.'
    }
    if (Test-Path -LiteralPath $destination) { throw "Refusing to overwrite: $destination" }
    if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source is a reparse point.' }
    $children = @(Get-ChildItem -LiteralPath $source -Force -Recurse)
    if (@($children | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw 'Reparse points require separate review; no move performed.'
    }
    $files = @($children | Where-Object { !$_.PSIsContainer } | ForEach-Object {
        @{ Relative = $_.FullName.Substring($source.Length + 1); Bytes = $_.Length;
           SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
    $records += @{ Source = $source; Destination = $destination; Status = 'planned';
                   FileCount = $files.Count; Bytes = ($files | Measure-Object Bytes -Sum).Sum; Files = $files }
    Write-Output ("{0} -> {1}; files={2}; bytes={3}" -f $source,$destination,$files.Count,($files | Measure-Object Bytes -Sum).Sum)
}
}
if (!$Execute) { Write-Output 'Dry run only. No files moved.'; return }
New-Item -ItemType Directory -Path $auditDir -Force | Out-Null
$records | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $auditFile -Encoding utf8
foreach ($record in $records) {
    # Move individual files atomically so a held directory handle cannot cause
    # PowerShell's recursive directory move to leave an untracked partial move.
    $sourceRoot = [IO.Path]::GetFullPath($record.Source).TrimEnd('\')
    $destinationRoot = [IO.Path]::GetFullPath($record.Destination).TrimEnd('\')
    $sourceDirs = @()
    foreach ($rootToCheck in @($sourceRoot, $destinationRoot)) {
        if (Test-Path -LiteralPath $rootToCheck) {
            $rootItem = Get-Item -LiteralPath $rootToCheck -Force
            if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
                @(Get-ChildItem -LiteralPath $rootToCheck -Force -Recurse -Attributes ReparsePoint).Count) { throw 'Unexpected source/destination reparse point.' }
        }
    }
    if (Test-Path -LiteralPath $sourceRoot) {
        $sourceDirs = @(Get-ChildItem -LiteralPath $sourceRoot -Force -Recurse -Directory)
        if (@($sourceDirs | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Unexpected reparse point.' }
    }
    foreach ($dir in $sourceDirs) {
        New-Item -ItemType Directory -Path (Join-Path $destinationRoot $dir.FullName.Substring($sourceRoot.Length + 1)) -Force | Out-Null
    }
    foreach ($file in $record.Files) {
        $sourcePath = [IO.Path]::GetFullPath((Join-Path $sourceRoot $file.Relative))
        $destinationPath = [IO.Path]::GetFullPath((Join-Path $destinationRoot $file.Relative))
        if (!$sourcePath.StartsWith($sourceRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or
            !$destinationPath.StartsWith($destinationRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe relative audit path.' }
        if (Test-Path -LiteralPath $destinationPath) {
            if ((Test-Path -LiteralPath $sourcePath) -or (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash -ne $file.SHA256) {
                throw "Ambiguous destination; no overwrite: $destinationPath"
            }
            continue
        }
        if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne $file.SHA256) { throw "Source changed: $sourcePath" }
        New-Item -ItemType Directory -Path (Split-Path -Parent $destinationPath) -Force | Out-Null
        [IO.File]::Move($sourcePath, $destinationPath)
    }
    $record.Status = 'moved_pending_verification'
    $records | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $auditFile -Encoding utf8
    $movedFiles = @(Get-ChildItem -LiteralPath $record.Destination -Force -Recurse -File)
    if ($movedFiles.Count -ne $record.FileCount) { throw 'Moved file set differs; preserve destination and inspect audit.' }
    foreach ($file in $record.Files) {
        $path = Join-Path $record.Destination $file.Relative
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $file.SHA256) {
            throw "Hash mismatch after move; no files deleted: $path"
        }
    }
    $record.Status = 'verified'
    # Preserve directory attributes and empty folders, then remove ONLY verified
    # empty old directories (no recursive delete). Locked empty roots can remain.
    foreach ($dir in $sourceDirs) {
        $target = Join-Path $destinationRoot $dir.FullName.Substring($sourceRoot.Length + 1)
        [IO.File]::SetAttributes($target, $dir.Attributes)
    }
    $removeDirs = @($sourceDirs | Sort-Object { $_.FullName.Length } -Descending | ForEach-Object { $_.FullName }) + @($sourceRoot)
    foreach ($dirPath in $removeDirs) {
        $resolved = [IO.Path]::GetFullPath($dirPath)
        if ($resolved -ne $sourceRoot -and !$resolved.StartsWith($sourceRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe empty-directory target.' }
        if ((Test-Path -LiteralPath $resolved) -and [IO.Directory]::GetFileSystemEntries($resolved).Length -eq 0) {
            try { [IO.Directory]::Delete($resolved, $false) }
            catch { Write-Warning "Verified files moved, but empty directory is locked: $resolved" }
        }
    }
    if (Test-Path -LiteralPath $sourceRoot) { $record.Status = 'verified_old_directories_remain' }
    $records | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $auditFile -Encoding utf8
    Write-Output ("VERIFIED: {0}; files={1}" -f $record.Destination,$record.FileCount)
}
