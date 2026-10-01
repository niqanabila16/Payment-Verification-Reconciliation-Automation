<#
.SYNOPSIS  Starts the development server on http://127.0.0.1:8000 (auto-reloads on code changes).
.USAGE     .\scripts\run.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
. .\.venv\Scripts\Activate.ps1
python manage.py migrate --no-input
python manage.py runserver 127.0.0.1:8000
