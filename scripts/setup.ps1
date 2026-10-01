<#
.SYNOPSIS
  One-time setup on Windows: virtual environment, dependencies, .env, database, demo data.
.USAGE
  PowerShell (from the project folder):
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\scripts\setup.ps1            # add -NoDemo to skip demo users and receipts
#>
param([switch]$NoDemo)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "1/6 Checking Python 3.12 ..." -ForegroundColor Cyan
$version = & py -3.12 --version 2>$null
if (-not $version) { throw "Python 3.12 was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH' and 'py launcher')." }
Write-Host "    $version"

Write-Host "2/6 Creating virtual environment (.venv) ..." -ForegroundColor Cyan
if (-not (Test-Path .venv)) { & py -3.12 -m venv .venv }
. .\.venv\Scripts\Activate.ps1

Write-Host "3/6 Installing dependencies ..." -ForegroundColor Cyan
python -m pip install --upgrade pip | Out-Null
pip install -r requirements.txt

Write-Host "4/6 Creating .env with a new secret key ..." -ForegroundColor Cyan
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  $key = python -c "import secrets; print(secrets.token_urlsafe(50))"
  (Get-Content .env) -replace "change-me-to-a-long-random-string", $key | Set-Content .env -Encoding utf8
} else { Write-Host "    .env already exists, left unchanged." }

Write-Host "5/6 Creating the database ..." -ForegroundColor Cyan
python manage.py migrate

if (-not $NoDemo) {
  Write-Host "6/6 Loading demo data ..." -ForegroundColor Cyan
  python manage.py seed_demo
} else {
  Write-Host "6/6 Create your first administrator:" -ForegroundColor Cyan
  python manage.py createsuperuser
}
Write-Host "`nDone. Start the site with:  .\scripts\run.ps1" -ForegroundColor Green
