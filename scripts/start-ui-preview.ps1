param([int]$Port = 5080, [string]$Python = '', [switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
if (!$Python) {
    $candidates = @((Join-Path $project '.venv/Scripts/python.exe'), (Join-Path (Split-Path $project -Parent) 'capstone-integration/.venv/Scripts/python.exe'))
    $Python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (!$Python) { throw 'Pass -Python with a Python environment containing requirements.txt.' }
$previewOutput = Join-Path $project 'output/ui-preview'
New-Item -ItemType Directory -Force -Path $previewOutput | Out-Null
$previewHost = if ($LocalOnly) { '127.0.0.1' } else { '0.0.0.0' }
$arguments = @(('"' + (Join-Path $PSScriptRoot 'run_ui_preview.py') + '"'), '--host', $previewHost, '--port', $Port)
$process = Start-Process -FilePath $Python -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $previewOutput 'server.log') -RedirectStandardError (Join-Path $previewOutput 'server-errors.log')
$process.Id | Set-Content -LiteralPath (Join-Path $previewOutput 'server.pid')
Write-Output "Operator interface: http://127.0.0.1:$Port (process $($process.Id)). Connect the Pi to record."
