<#
.SYNOPSIS
  Production-style server with Waitress (works on Windows). Use it on the central office computer.
  Needs DJANGO_DEBUG=False and a real DJANGO_SECRET_KEY in .env.
.USAGE
  .\scripts\serve.ps1 -Port 8000
#>
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. .\.venv\Scripts\Activate.ps1
python manage.py migrate --no-input
python manage.py collectstatic --no-input
python manage.py recover_imports --minutes 10          # clean up imports interrupted by the last shutdown
Write-Host "Serving on http://0.0.0.0:$Port (press Ctrl+C to stop)" -ForegroundColor Green
# 8 threads: enough for a few dozen branch users; the matching engine itself runs one job at a time.
waitress-serve --listen="0.0.0.0:$Port" --threads=8 config.wsgi:application
