<#
.SYNOPSIS  Copies the SQLite database to backups\ with a timestamp and keeps the newest 30 copies.
.USAGE     .\scripts\backup.ps1            (schedule it daily with Task Scheduler, see docs/MAINTENANCE.md)
#>
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force backups | Out-Null
. .\.venv\Scripts\Activate.ps1
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
# sqlite3's backup API gives a consistent copy even while the site is running.
python -c "import sqlite3,sys; s=sqlite3.connect('db.sqlite3'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close(); s.close()" "backups\db-$stamp.sqlite3"
Get-ChildItem backups\db-*.sqlite3 | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item
Write-Host "Backup written to backups\db-$stamp.sqlite3" -ForegroundColor Green
