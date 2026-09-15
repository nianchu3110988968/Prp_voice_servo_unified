$ErrorActionPreference = "Stop"
$serverRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$referencePath = Join-Path $serverRoot "voice_models\reference_short_20260907.wav"

if (-not (Test-Path -LiteralPath $referencePath)) {
    throw "Reference audio not found: $referencePath"
}

$env:PRP_TTS_BACKEND = "gpt_sovits"
$env:PRP_GPT_SOVITS_URL = "http://127.0.0.1:9880/tts"
$env:PRP_GPT_SOVITS_REFERENCE_WAV = $referencePath
$promptTextBase64 = "5L2g5aW977yM5oiR5Lya5LiA55u06Zmq552A5L2g44CC5LuK5aSp5Lmf6L6b6Ium5LqG77yM5YWI5LyR5oGv5LiA5LiL5ZCn44CC"
$env:PRP_GPT_SOVITS_PROMPT_TEXT = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String($promptTextBase64)
)
$env:PRP_GPT_SOVITS_PROMPT_LANGUAGE = "zh"
$env:PRP_GPT_SOVITS_TEXT_LANGUAGE = "zh"
$env:PRP_TTS_FALLBACK_TO_SAPI = "true"

Push-Location $serverRoot
try {
    python -m uvicorn ai_bridge_server:app --host 0.0.0.0 --port 8000
}
finally {
    Pop-Location
}
