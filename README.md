# Payment Verification & Reconciliation Automation
## Complete Setup Guide (Windows + Git Bash)

This package contains all planning documents, the database schema, sample data, configuration, and the project folder skeleton for the payment verification & reconciliation automation system. This guide walks you from **a completely empty laptop** to a working local development environment.

**Intended reader:** a developer (including a solo developer, see `docs/03-Solo-Delivery-Plan.docx`) picking up this project for the first time.

**Assumptions:** Windows 10/11, using **Git Bash** as your main terminal (not Command Prompt/PowerShell), an active internet connection, and a work email account already set up (for Microsoft 365).

---

## Table of Contents

1. [Package Structure](#1-package-structure)
2. [Stage 0 -- Install Base Tools](#stage-0)
3. [Stage 1 -- Extract the Package & Open It in Git Bash](#stage-1)
4. [Stage 2 -- Set Up a GitHub Account](#stage-2)
5. [Stage 3 -- Set Up Environment Variables (.env)](#stage-3)
6. [Stage 4 -- Run the Local Database (Docker)](#stage-4)
7. [Stage 5 -- Import the Database Schema & Sample Data](#stage-5)
8. [Stage 6 -- Verify the Database](#stage-6)
9. [Stage 7 -- Set Up Microsoft Forms + SharePoint List + Power Automate](#stage-7)
10. [Stage 8 -- Set Up an Azure AD App Registration (Graph API)](#stage-8)
11. [Stage 9 -- Set Up the Microsoft Teams Webhook (Notifications)](#stage-9)
12. [Stage 10 -- Try Out the Sample Data](#stage-10)
13. [Recommended Reading Order for the Documents](#11-recommended-reading-order)
14. [Common Troubleshooting](#12-common-troubleshooting)
15. [Cross-Reference: Decisions and Documents](#13-cross-reference)

---

## 1. Package Structure

```
payment-reconciliation-project/
├── README.md                          <- You are reading this file
├── docs/
│   ├── 01-Technical-Design-Document.docx
│   ├── 02-Agile-Delivery-Plan-Team.docx
│   ├── 03-Solo-Delivery-Plan.docx
│   ├── 04-Solo-Delivery-Plan-Finance-First.docx
│   └── adr/                           <- Architecture Decision Records (Nygard format)
│       ├── README.md
│       └── 0001 through 0008 ....md
├── database/
│   ├── schema.sql                     <- Full DDL (run this first)
│   ├── seed_sample_data.sql           <- Sample data for testing
│   └── ERD.md                         <- Entity & relationship explanation
├── samples/
│   ├── sample_bank_statement_RHB.xlsx
│   ├── sample_bank_statement_MAYBANK.xlsx
│   ├── sample_teller_strings.md
│   ├── sample_bank_format_config_RHB.json
│   └── sample_ocr_result.json
├── config/
│   ├── docker-compose.yml
│   └── .env.example
└── app-skeleton/                      <- Code folder structure (see Technical Design Document Section 24)
    ├── app/{api,ocr,formatter,bank_ingest,matching,notifications,models,config}/
    ├── workers/
    └── tests/{unit,integration,fixtures}/
```

---

<a name="stage-0"></a>
## Stage 0 -- Install Base Tools

> This step happens **before** Git Bash exists on your machine. Open **PowerShell** (right-click the Start Menu > "Windows PowerShell" or "Terminal") for this initial installation step only.

### 0.1 Install Git for Windows (includes Git Bash)

```powershell
winget install --id Git.Git -e --source winget
```

Once done, **close PowerShell**, then open **Git Bash** from the Start Menu (type "Git Bash"). **From this point on, every command in this guide is run from Git Bash**, unless stated otherwise.

Verify in Git Bash:

```bash
git --version
# example output: git version 2.46.0.windows.1
```

### 0.2 Install Python

```bash
winget install --id Python.Python.3.12 -e --source winget
```

Close and reopen Git Bash, then verify:

```bash
python --version
# or if that's not found:
python3 --version
```

### 0.3 Install Docker Desktop

```bash
winget install --id Docker.DockerDesktop -e --source winget
```

After installation finishes:
1. **Open the "Docker Desktop" app** from the Start Menu (it must be opened manually once, wait until its status shows "Running" in the system tray).
2. Docker Desktop on Windows requires **WSL2** -- if a prompt appears to install/enable WSL2, follow it and restart your computer if asked.

Verify from Git Bash (Docker Desktop must already be running):

```bash
docker --version
docker compose version
```

### 0.4 Install VS Code (optional, recommended)

```bash
winget install --id Microsoft.VisualStudioCode -e --source winget
```

> **If `winget` is not recognized:** your Windows version may be older. Download the installers manually from: Git -- https://git-scm.com/download/win , Python -- https://www.python.org/downloads/ , Docker Desktop -- https://www.docker.com/products/docker-desktop/ , VS Code -- https://code.visualstudio.com/download

---

<a name="stage-1"></a>
## Stage 1 -- Extract the Package & Open It in Git Bash

1. Extract this zip package using Windows Explorer (right-click > "Extract All...") to your working location, e.g. `D:\Projects\`.
2. Open Git Bash and navigate to the extracted folder:

```bash
cd /d/Projects/payment-reconciliation-project
# note: Git Bash maps D:\ to /d/, C:\ to /c/, and so on.
pwd
ls -la
```

You should see the `docs/`, `database/`, `samples/`, `config/`, `app-skeleton/` folders and this `README.md` file.

---

<a name="stage-2"></a>
## Stage 2 -- Set Up a GitHub Account

1. If you don't already have one, sign up at https://github.com
2. Generate an SSH key from Git Bash (so you can push without typing a password every time):

```bash
ssh-keygen -t ed25519 -C "your_email@company.com.my"
# press Enter 3 times to accept the defaults (skip a passphrase for speed, though a passphrase is more secure)
```

3. Copy the resulting public key:

```bash
cat ~/.ssh/id_ed25519.pub
```

4. Go to https://github.com/settings/keys > "New SSH key" > paste what you just copied > "Add SSH key".
5. Create a new repository on GitHub (private, since this concerns a financial system) -- click "New repository" at https://github.com/new
6. Back in Git Bash, initialize the local repo and push for the first time:

```bash
git init
git add .
git commit -m "Initial commit: project scaffold, docs, schema, samples"
git branch -M main
git remote add origin git@github.com:YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

> Replace `YOUR_USERNAME` and `YOUR_REPO_NAME` with your own. If `git push` asks you to confirm the SSH fingerprint the first time, type `yes`.

---

<a name="stage-3"></a>
## Stage 3 -- Set Up Environment Variables (.env)

```bash
cp config/.env.example config/.env
```

Open `config/.env` in VS Code (`code config/.env`) or another text editor, and adjust at minimum:
- `POSTGRES_PASSWORD` -- change it from `changeme_local_only` to something else for local use (not critical for local dev, but it's good practice not to keep the default).
- Leave the `AZURE_*`, `MS_GRAPH_*`, `WHATSAPP_*` variables commented out (`#`) for now -- those get filled in during Stages 7-9 and Phase 2.

> **IMPORTANT:** the `.env` file (not `.env.example`) will eventually contain real credentials -- **never** commit it to git. Add a `.env` line to `.gitignore`:

```bash
echo ".env" >> .gitignore
echo "config/.env" >> .gitignore
git add .gitignore
git commit -m "Ignore .env file"
```

---

<a name="stage-4"></a>
## Stage 4 -- Run the Local Database (Docker)

Make sure **Docker Desktop is running** (check the icon in the system tray), then from the project root folder:

```bash
cd config
docker compose up -d
```

Expected output: 3 containers running (`reconciliation_postgres`, `reconciliation_redis`, `reconciliation_pgadmin`). Check their status:

```bash
docker compose ps
```

All containers should show `running`/`healthy`. If any fail, check its logs:

```bash
docker compose logs postgres
```

---

<a name="stage-5"></a>
## Stage 5 -- Import the Database Schema & Sample Data

Go back to the project root folder:

```bash
cd ..
```

Import the schema (creates all tables):

```bash
docker exec -i reconciliation_postgres psql -U reconciliation_user -d reconciliation_db < database/schema.sql
```

Import the sample data:

```bash
docker exec -i reconciliation_postgres psql -U reconciliation_user -d reconciliation_db < database/seed_sample_data.sql
```

If both commands run without any `ERROR` messages, your database is now set up with the table structure plus a few rows of sample data.

---

<a name="stage-6"></a>
## Stage 6 -- Verify the Database

**Option A -- from the command line (psql):**

```bash
docker exec -it reconciliation_postgres psql -U reconciliation_user -d reconciliation_db -c "SELECT transaction_code, status FROM bot_transactions;"
docker exec -it reconciliation_postgres psql -U reconciliation_user -d reconciliation_db -c "SELECT match_level, match_score, match_status FROM reconciliations;"
```

You should see 2 rows in `bot_transactions` (MIR-20260908-00123 and -00124) and 1 matched row in `reconciliations` with `match_score = 99.00`.

**Option B -- from a browser (pgAdmin, easier to view visually):**

1. Open a browser to http://localhost:8081
2. Log in: email `admin@local.test`, password `admin` (per `config/docker-compose.yml`)
3. Click "Add New Server" -- General tab: Name = `Local`. Connection tab: Host = `postgres` (the service name in docker-compose, NOT `localhost`), Port = `5432`, Username = `reconciliation_user`, Password = whatever is in `config/.env`.
4. Once connected, navigate to Databases > reconciliation_db > Schemas > public > Tables -- right-click any table > "View/Edit Data" > "All Rows".

---

<a name="stage-7"></a>
## Stage 7 -- Set Up Microsoft Forms + SharePoint List + Power Automate

> This is the **interim** teller data-capture mechanism per `docs/adr/0008-teller-data-capture-mechanism.md`. Requires a work Microsoft 365 account and permission to create a Form/List/Flow -- if you're denied, contact your company's M365 admin.

### 7.1 Create a Microsoft Form

1. Go to https://forms.office.com, sign in with your work M365 account.
2. Click "New Form", title it "Teller Transaction Entry".
3. Add fields matching the `bot_transactions` columns in `database/schema.sql`:
   - "Sender Name" -- Text
   - "Destination Bank" -- Choice (populate options from `bank_code` in `bank_format_configs`, e.g.: RHB, MAYBANK)
   - "Amount (RM)" -- Text with the "Number" restriction
   - "Reference Number" -- Text (can be left blank)
   - "Entity/Business Name" -- Text (can be left blank)
4. Click the "..." icon in the top right > **Settings**:
   - "Who can fill out this form" -> select **"Only people in my organization"** (so the submitter's AD identity is captured automatically -- this is what gives you an audit trail without extra manual work).
   - Turn on **"Record name"**.
5. Share the form link with tellers (via Teams chat/internal email).

### 7.2 Create a SharePoint List

1. Open your finance team/department site at `https://[yourtenant].sharepoint.com/...`
2. Click "New" > "List" > "Blank list" -- name it `TellerTransactions`.
3. Add columns (click "+ Add column"), matching the data types of the form fields above:
   - `SenderName` -- Single line of text
   - `BankCode` -- Choice
   - `AmountRM` -- Currency or Number
   - `ReferenceNumber` -- Single line of text
   - `EntityName` -- Single line of text

### 7.3 Connect the Form to the List via Power Automate

1. Go to https://make.powerautomate.com, sign in with the same account.
2. Click "Create" > "Automated cloud flow".
3. Name the flow, and in the trigger search box look for **"Microsoft Forms"** > select **"When a new response is submitted"** > choose the "Teller Transaction Entry" form you just created > "Create".
4. Click "+ New step" > search for **"Microsoft Forms"** again > select **"Get response details"** > for Form Id pick the same form, for Response Id pick the dynamic content from the previous trigger.
5. Click "+ New step" > search for **"SharePoint"** > select **"Create item"** > enter the Site Address (your finance site) and List Name (`TellerTransactions`) > map each List column to the matching dynamic content from the form response (e.g. `SenderName` <- the "Sender Name" answer).
6. Click "Save", then submit a test response on the form -- check that a new item automatically appears in the SharePoint List.

> "Microsoft Forms" and "SharePoint - Create item" are **standard connectors (not premium)** -- no additional Power Automate Premium license is needed, per `docs/adr/0008-teller-data-capture-mechanism.md`.

---

<a name="stage-8"></a>
## Stage 8 -- Set Up an Azure AD App Registration (for Backend Polling via Graph API)

> This is what lets our backend programmatically read the contents of the SharePoint List. Requires an Azure AD/Entra ID admin role -- if you're not an admin, ask your IT team to perform this step and give you the results from point 5.

1. Go to https://portal.azure.com, search for **"App registrations"** > **"New registration"**.
2. Give it a name (e.g. `reconciliation-backend-graph`), choose **"Accounts in this organizational directory only"** > "Register".
3. On the new app's Overview page, note down:
   - **Application (client) ID**
   - **Directory (tenant) ID**
4. Go to **"Certificates & secrets"** > "New client secret" > add a description & expiry > "Add". **Copy the secret's Value right away** (it will not be shown again once you navigate away).
5. Go to **"API permissions"** > "Add a permission" > "Microsoft Graph" > "Application permissions" > find and check **`Sites.Read.Write.All`** (or a narrower scope if a site-specific one is available) > "Add permissions".
6. Click **"Grant admin consent for [your organization]"** -- **this requires an admin role**, and is the approval checkpoint referenced in `docs/01-Technical-Design-Document.docx` Section 20.
7. Enter the results of points 3-4 into `config/.env`:

```bash
# in config/.env
MS_GRAPH_TENANT_ID=<Directory tenant ID from step 3>
MS_GRAPH_CLIENT_ID=<Application client ID from step 3>
MS_GRAPH_CLIENT_SECRET=<Client secret value from step 4>
```

For `MS_SHAREPOINT_SITE_ID` and `MS_SHAREPOINT_LIST_ID`, the fastest way is to use Graph Explorer (https://developer.microsoft.com/en-us/graph/graph-explorer), sign in with the same account, then run the query `GET https://graph.microsoft.com/v1.0/sites/{hostname}:/sites/{site-path}` to get the Site ID, followed by `GET /sites/{site-id}/lists` to get the List ID for `TellerTransactions`.

---

<a name="stage-9"></a>
## Stage 9 -- Set Up the Microsoft Teams Webhook (Notifications)

> **Important note:** the old "Connectors > Incoming Webhook" method in Teams **was officially retired by Microsoft as of May 2026** and no longer works. The steps below use the current official replacement, the **Workflows app**. If you come across other tutorials online that mention "Connectors," ignore them -- they're outdated.

1. Open Microsoft Teams, go to the finance channel you want notifications sent to.
2. Click the **"..."** icon next to the channel name > select **"Workflows"**.
3. Look for the official template **"Post to a channel when a webhook request is received"** (built on the "When a Teams webhook request is received" trigger).
4. Follow the wizard: name the workflow, confirm the destination channel matches what you opened in step 1 > finish creating it.
5. Once done, a **Webhook URL** will be shown -- copy it.
6. Add it to `config/.env`:

```bash
TEAMS_WEBHOOK_URL=<paste the URL here>
```

7. Test it manually from Git Bash (simple Adaptive Card payload):

```bash
curl -H "Content-Type: application/json" -d '{
  "type": "message",
  "attachments": [{
    "contentType": "application/vnd.microsoft.card.adaptive",
    "content": {
      "type": "AdaptiveCard",
      "version": "1.4",
      "body": [{"type": "TextBlock", "text": "Local setup test notification succeeded.", "wrap": true}]
    }
  }]
}' "$TEAMS_WEBHOOK_URL"
```

If it works, the message "Local setup test notification succeeded." will appear in the Teams channel you selected.

---

<a name="stage-10"></a>
## Stage 10 -- Try Out the Sample Data

Check the sample files available for development:

```bash
ls -la samples/
```

- `sample_bank_statement_RHB.xlsx` and `sample_bank_statement_MAYBANK.xlsx` -- two different column formats, for testing that the bank parser is genuinely data-driven (see the `bank_format_configs` table in `database/schema.sql`).
- `sample_teller_strings.md` -- example teller string formats, including one that requires sanitizing a "/" character.
- `sample_ocr_result.json` -- an example of the OCR result data structure (used starting in Phase 2).

Compute a file's SHA256 hash (used for the idempotency mechanism in `bank_file_batches.file_hash`, see `docs/adr/0005-bank-ingestion-via-xlsx-folder.md`):

```bash
sha256sum samples/sample_bank_statement_RHB.xlsx
```

Run the same command twice on the same file and compare -- the hash must be identical. This is the principle the file watcher relies on to detect files that have already been processed.

---

## 11. Recommended Reading Order

If you're new to this project, read the documents in this order so the context builds up properly:

| Order | Document | Why |
|---|---|---|
| 1 | `docs/01-Technical-Design-Document.docx` | Full architecture & technical design -- the foundation for every other decision |
| 2 | `docs/adr/README.md`, then ADRs 0001-0008 | The key decisions and their reasoning, a condensed version of the design document |
| 3 | `docs/04-Solo-Delivery-Plan-Finance-First.docx` | The delivery plan **currently in use** (finance-first revision, OCR deferred) |
| 4 | `docs/03-Solo-Delivery-Plan.docx` | The original solo plan (OCR-first) -- for context, partly superseded by ADR-0007 |
| 5 | `docs/02-Agile-Delivery-Plan-Team.docx` | The plan for if the project later scales to a team instead of staying solo |
| 6 | `database/ERD.md` + `database/schema.sql` | Data-structure detail, once you understand the bigger design |

---

## 12. Common Troubleshooting

| Problem | Solution |
|---|---|
| `winget` not recognized in Git Bash | Make sure you ran it from PowerShell for the initial install (Stage 0), or update Windows/App Installer via the Microsoft Store |
| `docker: command not found` | Docker Desktop hasn't been opened -- open the app from the Start Menu, wait for "Running" status in the tray, then try again |
| `port is already allocated` when running `docker compose up` | Another app is using port 5432/6379/8081 -- close that app, or change the port mapping in `config/docker-compose.yml` (e.g.: `"5433:5432"`) |
| `psql: FATAL: password authentication failed` | The password in the command doesn't match `config/.env` -- double-check `POSTGRES_PASSWORD` |
| Git Bash won't `cd` into another drive (D:, E:) | Use the format `/d/folder_name`, not `D:\folder_name` |
| `git push` fails with `Permission denied (publickey)` | The SSH key hasn't been added to GitHub (redo Stage 2, points 3-4), or the public key was pasted incorrectly (make sure you copy the whole line, including the leading `ssh-ed25519`) |
| The `.xlsx` sample files won't open cleanly | Open them with Excel/LibreOffice Calc (double-click), not a text editor -- these are real binary Excel files |
| Garbled line endings (`^M` at the end of lines) when editing files in Git Bash | Run `git config --global core.autocrlf true` before your next clone/commit |

---

## 13. Cross-Reference

If you find something in the code/database and want to know **why** it was designed that way, here's a quick map:

| What You See | Find the Reason In |
|---|---|
| The `entry_source` column on the `bot_transactions` table | `docs/adr/0008-teller-data-capture-mechanism.md` |
| No table related to a Virtual Account | `docs/adr/0004-no-virtual-account.md` |
| All amounts stored as INTEGER (minor units), not FLOAT | `docs/01-Technical-Design-Document.docx` Section 15.1 |
| `match_score` and `match_level` on `reconciliations` | `docs/01-Technical-Design-Document.docx` Sections 15-16, `docs/adr/0003-deterministic-matching-not-ml.md` |
| The `app/ocr/` folder is still empty | `docs/adr/0007-finance-first-sequencing.md` -- OCR isn't built until Phase 2 |
| Why notifications go to Teams, not a WhatsApp group | `docs/adr/0006-teams-not-whatsapp-group-for-internal-notification.md` |
| Why there are 2 bank samples with different column formats | To confirm `bank_format_configs` is genuinely data-driven, see `docs/01-Technical-Design-Document.docx` Section 13 |
| Why `finance_users` only has 2 roles (not 4) | `docs/03-Solo-Delivery-Plan.docx` Section 4 -- the MVP-Solo scope was trimmed down |

---

Happy building. If any step in this guide becomes outdated (a Microsoft menu changes again, a new tool version comes out, etc.), update this file and, if it changes an architectural decision rather than just a technical step, record that change as a new ADR (see `docs/adr/README.md`, "How to Add a New ADR").
