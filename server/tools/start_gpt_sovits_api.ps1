param([string]$GptSovitsRoot = "", [string]$Role = "New_ManBoo")
$ErrorActionPreference = "Stop"
$entry = Join-Path $PSScriptRoot "role_service.py"
$arguments = @("-X", "utf8", $entry, "gpt_sovits", "--role", $Role)
if ($GptSovitsRoot) { $arguments += @("--gpt-sovits-root", $GptSovitsRoot) }
& python @arguments
exit $LASTEXITCODE
