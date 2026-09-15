param([string]$GptSovitsRoot = 'E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604')
$ErrorActionPreference = 'Stop'
if (Get-NetTCPConnection -LocalPort 9872 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 9872 is already in use. Do not start a duplicate inference service.'
}
$pythonPath = Join-Path $GptSovitsRoot 'runtime\python.exe'
$env:version = 'v2ProPlus'
$env:gpt_path = Join-Path $GptSovitsRoot 'GPT_SoVITS\pretrained_models\s1v3.ckpt'
$env:sovits_path = Join-Path $GptSovitsRoot 'GPT_SoVITS\pretrained_models\v2Pro\s2Gv2ProPlus.pth'
$env:PRP_DISABLE_CUDA_GRAPH = '1'
$env:infer_ttswebui = '9872'
$env:is_share = 'False'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
foreach ($requiredPath in @($pythonPath, $env:gpt_path, $env:sovits_path)) {
    if (!(Test-Path -LiteralPath $requiredPath)) { throw "Missing: $requiredPath" }
}
Push-Location $GptSovitsRoot
try {
    & $pythonPath 'GPT_SoVITS\inference_webui.py' 'zh_CN'
    if ($LASTEXITCODE -ne 0) { throw "Inference exited with code $LASTEXITCODE" }
} finally { Pop-Location }
