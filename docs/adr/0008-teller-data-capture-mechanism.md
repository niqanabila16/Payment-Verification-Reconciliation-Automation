# ADR-0008: Microsoft Forms + SharePoint (Interim), Migrating to a Custom Web Form (Target) -- Not Google Forms or Third-Party Form Builders

## Status

Accepted

## Context

With OCR deferred (ADR-0007), the system still needs a reliable way to capture structured transaction data on the customer/teller side for matching. The WhatsApp bot currently in operation only replies to customers and cannot be relied on as a source of exportable structured data. Several form-building tools were evaluated (Google Forms, Microsoft Forms, a SharePoint List, Power Apps, a custom-built web form, and third-party form builders such as Typeform/JotForm). The company operates in a Microsoft 365 environment with strict security requirements, which rules out any tool that moves financial transaction data outside the governed tenant.

## Decision

In the near term, teller data entry will use Microsoft Forms with responses routed to a SharePoint List/Excel table (via a standard, non-premium Power Automate connector), which our backend polls via the Microsoft Graph API -- reusing the same ingestion pattern already planned for bank XLSX files. Once the core backend is live (around Milestone 3-4), this will be replaced by a custom-built web form served directly by our own backend, giving real-time capture and full control over validation/RBAC/audit logging. Google Forms and third-party form builders (Typeform, JotForm, Airtable Forms, etc.) are explicitly rejected because they move financial data outside the audited Microsoft tenant. Power Apps is not used for this purpose because its per-user licensing cost (USD 10-20/user/month as of the January 2026 pricing changes) is disproportionate to the simplicity of the form needed.

## Consequences

The near-term capture mechanism ships quickly with zero additional licensing cost and stays within the already-approved Microsoft security posture; it reuses the Graph API integration pattern already planned elsewhere, avoiding a new integration pattern; the long-term target state gives full real-time control with no recurring per-user cost. On the other hand, the interim solution has polling latency (not real-time) and still depends on the same Graph API app-registration approval dependency noted in the main technical design; the system temporarily depends on two different data-capture mechanisms during the migration window, requiring both to be tested and the first one to be cleanly deprecated once migration is complete.
