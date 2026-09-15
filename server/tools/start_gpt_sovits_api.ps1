param(
    [string]$GptSovitsRoot = "E:\AI\GPTSoVITS\GPT-SoVITS-v2pro-20250604"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$configPath = Join-Path $projectRoot "server\configs\gpt_sovits_v2proplus.yaml"
$pythonPath = Join-Path $GptSovitsRoot "runtime\python.exe"
$apiPath = Join-Path $GptSovitsRoot "api_v2.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "GPT-SoVITS runtime not found: $pythonPath"
}

Push-Location $GptSovitsRoot
try {
    & $pythonPath $apiPath -a 127.0.0.1 -p 9880 -c $configPath
}
finally {
    Pop-Location
}
