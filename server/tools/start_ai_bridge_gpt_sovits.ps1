param([string]$Role = "New_ManBoo")
$ErrorActionPreference = "Stop"
& python -X utf8 (Join-Path $PSScriptRoot "role_service.py") bridge --role $Role
exit $LASTEXITCODE
