param([string]$GptSovitsRoot = 'E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604')
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$datasetRoot = Join-Path $projectRoot 'voice_data\manbo'
if (Get-NetTCPConnection -LocalPort 9874 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 9874 is already in use. Reuse the existing training page; do not start a duplicate.'
}
$pythonPath = Join-Path $GptSovitsRoot 'runtime\python.exe'
$env:PRP_GSV_VERSION = 'v2ProPlus'
$env:PRP_EXPERIMENT_NAME = 'manbo'
$env:PRP_DATASET_LIST = Join-Path $datasetRoot 'clips.list'
$env:PRP_DATASET_AUDIO = Join-Path $datasetRoot 'clips'
$env:PRP_FULL_TEXT_PATH = Join-Path $datasetRoot 'full_text.txt'
$env:PRP_FEATURE_GPU = '0'
$env:PRP_TRAIN_NUM_WORKERS = '0'
$env:PRP_GPT_NUM_WORKERS = '1'
$env:PRP_KEEP_TEMP = '1'
$env:PRP_DISABLE_CUDA_GRAPH = '1'
$env:PRP_MAIN_TITLE = 'MANBO Training - 9874'
$env:PRP_ANNOTATION_TITLE = 'MANBO Text Proofreading - 9871'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
$env:PATH = (Join-Path $GptSovitsRoot 'runtime') + ';' + $env:PATH
foreach ($requiredPath in @($pythonPath, $env:PRP_DATASET_LIST, $env:PRP_DATASET_AUDIO, $env:PRP_FULL_TEXT_PATH)) {
    if (!(Test-Path -LiteralPath $requiredPath)) { throw "Missing: $requiredPath" }
}
Write-Host 'Training page: http://127.0.0.1:9874/ (open in your external browser)'
Write-Host "Dataset: $datasetRoot"
Write-Host 'This starts the training UI only. It does not start training or change robot TTS.'
Push-Location $GptSovitsRoot
try {
    & $pythonPath '-u' '-I' 'webui.py' 'zh_CN'
    if ($LASTEXITCODE -ne 0) { throw "Training UI exited with code $LASTEXITCODE" }
} finally { Pop-Location }
