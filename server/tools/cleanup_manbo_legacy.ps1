param([switch]$Execute)
$ErrorActionPreference = 'Stop'
$projectRoot = 'E:\Projects2026\Prp_voice_servo_unified'
$gsvRoot = 'E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604'
$datasetRoot = Join-Path $projectRoot 'voice_data\manbo'
$journalPath = Join-Path $projectRoot 'docs\工作留档\manbo_cleanup_20260915.json'
$protected = @($datasetRoot, (Join-Path $projectRoot 'server\voice_models'),
    (Join-Path $projectRoot 'server\configs'), (Join-Path $gsvRoot 'GPT_SoVITS\pretrained_models'),
    'C:\Users\ASUS\Downloads\三月七')

function Under([string]$Path, [string]$Root) {
    return $Path.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}
function FilesAt([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point rejected: $Path" }
    $all = @($item)
    if ($item.PSIsContainer) { $all += @(Get-ChildItem -LiteralPath $Path -Recurse -Force) }
    foreach ($entry in $all) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Nested reparse point rejected: $($entry.FullName)" }
    }
    return @($all | Where-Object { -not $_.PSIsContainer } | Sort-Object FullName | ForEach-Object {
        [pscustomobject]@{path=$_.FullName; bytes=$_.Length; utc_ticks=$_.LastWriteTimeUtc.Ticks}
    })
}
function ValidateTarget([string]$Path) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path.TrimEnd('\')
    if ($resolved -ne $Path.TrimEnd('\')) { throw "Unexpected resolved path: $Path => $resolved" }
    foreach ($keep in $protected) {
        if ($resolved -eq $keep -or (Under $resolved $keep) -or (Under $keep $resolved)) {
            throw "Protected path overlap: $resolved"
        }
    }
    $allowed = (Under $resolved (Join-Path $gsvRoot 'output')) -or
        (Under $resolved (Join-Path $gsvRoot 'logs')) -or
        (Under $resolved (Join-Path $gsvRoot 'GPT_weights_v2ProPlus')) -or
        (Under $resolved (Join-Path $gsvRoot 'SoVITS_weights_v2ProPlus')) -or
        (Under $resolved (Join-Path $gsvRoot 'TEMP\gradio')) -or
        ($resolved -eq (Join-Path $gsvRoot 'TEMP_backup_before_training_ui_20260915_095344')) -or
        (Under $resolved (Join-Path $projectRoot 'server')) -or
        ($resolved -in @('C:\Users\ASUS\Downloads\11_曼波10分钟台词(1)',
            'C:\Users\ASUS\Downloads\曼波配音视频傻瓜式教学.mp4', 'C:\Users\ASUS\Downloads\audio.wav'))
    if (-not $allowed) { throw "Target outside explicit task areas: $resolved" }
}

# Always verify the retained corpus immediately before any cleanup.
$dataset = Get-Content -LiteralPath (Join-Path $datasetRoot 'dataset.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($clip in $dataset.clips) {
    if ((Get-FileHash -LiteralPath $clip.file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $clip.sha256) {
        throw "Retained audio changed: $($clip.file)"
    }
}
if ((Get-FileHash -LiteralPath (Join-Path $datasetRoot 'full_audio.wav')).Hash.ToLowerInvariant() -ne $dataset.full_audio_sha256) {
    throw 'Retained continuous audio hash mismatch'
}
if ((Get-FileHash -LiteralPath (Join-Path $datasetRoot 'clips.list')).Hash.ToLowerInvariant() -ne $dataset.initial_clips_list_sha256) {
    throw 'Retained annotation changed since consolidation; review before cleanup'
}
if (-not $Execute) {
    if (Test-Path -LiteralPath $journalPath) { throw 'Cleanup plan already exists; refusing overwrite' }
    $targets = @(
        (Join-Path $gsvRoot 'output\nuonuo_mambo_video_v1'),
        (Join-Path $gsvRoot 'output\nuonuo_mambo_v1'),
        (Join-Path $gsvRoot 'logs\manbo_narrator_zh_v1'),
        (Join-Path $gsvRoot 'logs\manbo_narrator_zh_v2_corrected'),
        (Join-Path $gsvRoot 'TEMP_backup_before_training_ui_20260915_095344'),
        'C:\Users\ASUS\Downloads\11_曼波10分钟台词(1)',
        'C:\Users\ASUS\Downloads\曼波配音视频傻瓜式教学.mp4'
    )
    foreach ($weightDir in @('GPT_weights_v2ProPlus','SoVITS_weights_v2ProPlus')) {
        $targets += @(Get-ChildItem -LiteralPath (Join-Path $gsvRoot $weightDir) -File |
            Where-Object { $_.Name -match '^manbo_narrator_zh_v(1|2_corrected)[_-].+\.(pth|ckpt)$' } |
            Select-Object -ExpandProperty FullName)
    }
    $targets += @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'server') -File |
        Where-Object {$_.Name -match '^(manbo_(v2_pipeline|zeroshot).*|annotation_(ui|recovery)_20260914.*|training_ui_202609(14|15)_[0-9]+)\.(out|err)\.log$'} |
        Select-Object -ExpandProperty FullName)
    $targets += @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'server\recordings') -File |
        Where-Object { $_.Name -match '^manbo_(v2_corrected_audition_20260914|zeroshot_20260915_sample0[12])\.wav$' } |
        Select-Object -ExpandProperty FullName)
    $knownDownload = Get-Item -LiteralPath 'C:\Users\ASUS\Downloads\audio.wav' -ErrorAction SilentlyContinue
    if ($knownDownload -and $knownDownload.Length -eq 247084 -and $knownDownload.LastWriteTime.ToString('yyyyMMddHHmmss') -eq '20260914235836') {
        $targets += $knownDownload.FullName
    }
    foreach ($cache in @(Get-ChildItem -LiteralPath (Join-Path $gsvRoot 'TEMP\gradio') -Directory -ErrorAction SilentlyContinue)) {
        $files = @(Get-ChildItem -LiteralPath $cache.FullName -Recurse -File)
        if ($files.Count -gt 0 -and @($files | Where-Object {$_.Name -notlike 'mambo_tutorial_audio_44100hz_mono.wav_*.wav'}).Count -eq 0) {
            $targets += $cache.FullName
        }
    }
    $entries = @()
    foreach ($target in ($targets | Sort-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $target)) { continue }
        ValidateTarget $target
        $files = @(FilesAt $target)
        $entries += [pscustomobject]@{path=$target; status='planned'; files=$files; bytes=($files | Measure-Object bytes -Sum).Sum}
    }
    $plan = [pscustomobject]@{created=(Get-Date -Format o); mode='recycle_bin_only'; protected=$protected; targets=$entries}
    [IO.File]::WriteAllText($journalPath, ($plan | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    $entries | Select-Object path,bytes | Format-Table -AutoSize | Out-String -Width 260 | Write-Output
    "PLAN_ONLY targets=$($entries.Count) bytes=$(($entries | Measure-Object bytes -Sum).Sum)"
    exit 0
}
$plan = Get-Content -LiteralPath $journalPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($plan.mode -ne 'recycle_bin_only') { throw 'Unexpected cleanup mode' }
foreach ($entry in $plan.targets) {
    if ($entry.status -ne 'planned') { throw 'Journal already used; inspect manually instead of repeating' }
    ValidateTarget $entry.path
    $current = @(FilesAt $entry.path)
    if (($current | ConvertTo-Json -Depth 4 -Compress) -cne (@($entry.files) | ConvertTo-Json -Depth 4 -Compress)) {
        throw "Target changed since reviewed plan: $($entry.path)"
    }
}
Add-Type -AssemblyName Microsoft.VisualBasic
foreach ($entry in $plan.targets) {
    try {
        $item = Get-Item -LiteralPath $entry.path
        if ($item.PSIsContainer) {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($entry.path,
                [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
                [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException)
        } else {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($entry.path,
                [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
                [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException)
        }
        if (Test-Path -LiteralPath $entry.path) { throw "Target still exists: $($entry.path)" }
        $entry.status = 'recycled'
        "RECYCLED $($entry.path)"
    } finally {
        [IO.File]::WriteAllText($journalPath, ($plan | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    }
}
"COMPLETE targets=$($plan.targets.Count)"
