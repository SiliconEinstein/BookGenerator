$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$service = Join-Path $PSScriptRoot "ppt_service.py"
$requestFile = Join-Path $PSScriptRoot "sample_request.json"

Write-Host "Starting ppt service..."
$proc = Start-Process -FilePath python -ArgumentList $service -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

try {
  $body = Get-Content -Raw -Encoding UTF8 $requestFile
  $resp = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:18765/api/ppt/generate" -ContentType "application/json; charset=utf-8" -Body $body
  $resp | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot "last_response.json")
  Write-Host "Done. Response written to tools/last_response.json"
}
finally {
  if (!$proc.HasExited) {
    Stop-Process -Id $proc.Id -Force
  }
}
