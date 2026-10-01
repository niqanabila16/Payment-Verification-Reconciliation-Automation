# Payment Verification & Reconciliation Automation

Web application that checks customer payments reported by branch **Tellers** against the **bank statements**
downloaded by **Finance**, flags typos and differences, and keeps an audit trail.

* Python **3.12**, Django **5.2 LTS**, RapidFuzz, SQLite (default) or PostgreSQL
* English-only UI, modern accessible design (WCAG 2.2 AA), no external CDNs or paid services
* Works on Windows with PowerShell (instructions below). Setup takes about 10 minutes.

| Role | What they do |
|---|---|
| Teller | Enter receipts (works offline and syncs later), see results, answer Finance |
| Finance | Upload bank statements, review typos / differences / not found, approve or send feedback |
| Admin | Manage users and roles, reset passwords, read the audit trail |

> Documentation map: [Architecture](docs/ARCHITECTURE.md) | [Requirements traceability](docs/REQUIREMENTS_TRACEABILITY.md) |
> [UI standards](docs/UI_STANDARDS.md) | [Maintenance, testing and troubleshooting](docs/MAINTENANCE.md) | [Database notes](docs/DATABASE.md)

---

## 1. Prerequisites (Windows 10/11)

1. **Python 3.12** from <https://www.python.org/downloads/windows/>. In the installer tick **"Add python.exe to PATH"**
   and keep the **py launcher** option.
2. **PowerShell** (built in). Open it with *Start > "Windows PowerShell"*.
3. Verify:

```powershell
py -3.12 --version        # expected: Python 3.12.x
```

## 2. Quick start (recommended): one script

```powershell
cd C:\path\to\payment-reconciliation
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass     # allows scripts for THIS window only
.\scripts\setup.ps1
.\scripts\run.ps1
```

Open <http://127.0.0.1:8000> and sign in with a demo account (password `Demo-Pass-2026!`):

| Role | Email |
|---|---|
| Admin | `admin@demo.test` |
| Finance | `finance@demo.test` |
| Teller (branch KJ) | `teller.kj@demo.test` |
| Teller (branch PJ) | `teller.pj@demo.test` |

**Try the whole flow in 2 minutes**

1. Sign in as `finance@demo.test` > **Bank statements** > choose bank *Bank Mandiri* > select
   `sample_data\mandiri_statement_2026-09-30.csv` > **Upload and match**.
2. Watch the progress bar. The result shows: 5 Match (GFP), 1 Typo, 1 Manual review, 1 Not found.
3. Open **Reconciliation**. Click the typo item: the side-by-side view shows identical fields in green and
   different fields in red, with the differing characters of the reference underlined.
4. Approve it, or send feedback to the teller. Sign in as `teller.kj@demo.test` to see the notification, correct the receipt and watch it re-match.

> Demo data is for trying the system only. For real use run `.\scripts\setup.ps1 -NoDemo` (creates your first administrator instead).

## 3. Manual setup (what the script does, step by step)

```powershell
# 1. Go to the project folder
cd C:\path\to\payment-reconciliation

# 2. Create and activate a virtual environment (isolated Python packages)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
#    If you see "running scripts is disabled on this system":
#    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass     (then activate again)

# 3. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Create your configuration file and set a secret key
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
notepad .env                                   # paste the key after DJANGO_SECRET_KEY=

# 5. Create the database tables
python manage.py migrate

# 6a. Demo data (optional)                      6b. Or create your own first administrator
python manage.py seed_demo                      python manage.py createsuperuser

# 7. Run
python manage.py runserver                      # http://127.0.0.1:8000
```

Stop the server with **Ctrl+C**. Next time only run steps 2 (activate) and 7.
Deactivate the environment with `deactivate`.

## 4. Run the automated tests

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py test                 # 81 tests, about 2 seconds
python manage.py test apps.reconciliation -v 2      # one app, verbose
python manage.py check --deploy       # security checklist (run with DJANGO_DEBUG=False)
```

## 5. Project layout

```
config/                 Django settings, root URLs, WSGI
apps/
  accounts/             Branch + User models, sign-in, Admin user management, throttling
  core/                 Bank, AuditLog, Notification, middleware, template tags, seed_demo command
  receipts/             Teller receipt form, validation, list/detail/edit, offline sync endpoint
  reconciliation/       Statement parser, matching engine, importer, Finance review services and screens
    services/           parser.py  engine.py  importer.py  review.py  submissions.py  notify.py
templates/              Django templates (components/ holds reusable alert, field, dialog, pagination)
static/css/app.css      Design system (tokens, components)
static/js/              app.js (site-wide), receipts.js (offline queue), import_progress.js, sw.js (service worker)
static/img/             architecture.svg, favicon
sample_data/            Demo bank statement (CSV + XLSX) and the script that builds them
scripts/                setup.ps1  run.ps1  serve.ps1  backup.ps1
docs/                   Architecture, traceability, UI standards, maintenance, database notes
```

## 6. Configuration (.env)

| Variable | Default | Meaning |
|---|---|---|
| `DJANGO_SECRET_KEY` | (must set) | Signs sessions. Keep it stable and secret. |
| `DJANGO_DEBUG` | `True` | Use `False` in production. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Add the central computer's host name / IP for branches. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | e.g. `https://recon.company.local` when behind HTTPS. |
| `DB_ENGINE` | `sqlite` | `postgres` to use PostgreSQL (see below). |
| `NOTIFY_BY_EMAIL` | `False` | Send an e-mail digest to tellers after each run (needs SMTP settings). |
| `MATCH_TYPO_MIN_SCORE` | `80` | Minimum RapidFuzz similarity for a typo suggestion. |
| `RECHECK_WINDOW_DAYS` | `31` | How long the engine keeps re-checking unmatched receipts (BR-10). |
| `REFERENCE_MIN_LENGTH` / `MAX` | `6` / `20` | Allowed length of the bank reference (NFR-PERF-2). |

Business rule values live in `config/settings.py` and are explained in [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md).

## 7. Deploy on the central office computer (Windows)

The central computer is switched off at night, so Tellers' browsers queue receipts and sync them in the morning.

```powershell
# .env: DJANGO_DEBUG=False, a real DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS=<host-or-ip>,localhost
.\scripts\serve.ps1 -Port 8000            # Waitress server, serves static files itself

# Let branches reach it (run PowerShell as Administrator, once)
New-NetFirewallRule -DisplayName "Payment Reconciliation" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow

# Start automatically when the computer boots (run PowerShell as Administrator, once)
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\path\to\payment-reconciliation\scripts\serve.ps1"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "Payment Reconciliation" -Action $action -Trigger $trigger -RunLevel Highest

# Daily database backup at 18:00
$backup = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\path\to\payment-reconciliation\scripts\backup.ps1"
Register-ScheduledTask -TaskName "Payment Reconciliation Backup" -Action $backup -Trigger (New-ScheduledTaskTrigger -Daily -At 6pm)
```

**HTTPS matters for two features.** Browsers allow the service worker (offline form) and desktop notifications only on
`https://` or `http://localhost`. With plain `http://<office-pc-ip>:8000` the site works, the offline queue still stores
receipts typed while the page is open, but the page cannot be opened while the server is off, and desktop alerts are
unavailable. Put a reverse proxy with an internal certificate in front (for example Caddy or IIS with a company CA certificate)
and add the HTTPS address to `DJANGO_CSRF_TRUSTED_ORIGINS`.

### Using PostgreSQL instead of SQLite

```powershell
pip install -r requirements-postgres.txt
# In .env set: DB_ENGINE=postgres, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
# Create the empty database first (pgAdmin or:  psql -U postgres -c "CREATE DATABASE payment_reconciliation;")
python manage.py migrate
```

PostgreSQL support follows the DBML schema but was not run in the automated tests here (they use SQLite). Run `python manage.py test` against your PostgreSQL server before go-live.

## 8. First-day checklist for real use

1. `.\scripts\setup.ps1 -NoDemo` and create the first administrator.
2. Sign in as that administrator > **Users** > add Finance and Teller accounts (each Teller needs a branch). A temporary password is shown once.
3. Add branches and banks (master data). Until an admin screen exists for these, use:
   ```powershell
   python manage.py shell -c "from apps.accounts.models import Branch; from apps.core.models import Bank; Branch.objects.get_or_create(code='KJ', defaults={'name':'Kajang'}); Bank.objects.get_or_create(code='MANDIRI', defaults={'name':'Bank Mandiri'})"
   ```
4. Download one real statement from the bank and upload it. If the header is not on row 4 the screen tells you exactly what to fix.

## 9. Known limitations (read before go-live)

* **No bank API** (constraint). Finance downloads and uploads the statement. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#where-would-automation-plug-in) for where an automated feed would plug in.
* **Single server process.** The import runs in a background thread and a lock allows one matching run at a time. Do not start several server processes on the same database; use Redis + RQ (planned Phase 2) before scaling out.
* **Desktop alerts** reach users while the site is open in a browser tab/window (even in the background). Users who closed the browser are reached by the optional e-mail digest. True push to a closed browser needs Web Push (future work).
* **Branches and banks have no admin screen yet**; add them with the command in section 8.
* **Visual check**: the interface was verified through automated rendering tests and a live HTTP run, not in every browser. Do a quick pass in Edge and Chrome on a branch computer.
* PowerShell scripts were written for Windows PowerShell 5.1 and PowerShell 7 but could not be executed in the build environment; the manual steps in section 3 are the reference.
