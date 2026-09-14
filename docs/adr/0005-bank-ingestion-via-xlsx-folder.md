# ADR-0005: Bank Data Ingestion via Manual XLSX Download + Folder Automation, Not a Direct Bank API

## Status

Accepted

## Context

Direct (host-to-host) API integration with each bank is not available for the MVP -- there is no existing technical partnership, and setting one up is a significant undertaking per bank. Finance currently downloads transaction data manually from internet banking in XLSX format.

## Decision

For the MVP, the system will not attempt direct bank API integration. Instead, finance will continue to manually download the XLSX file and drop it into a monitored secure folder; an automated pipeline (file watcher with readiness checks, hash-based idempotency, per-bank column mapping, normalization) takes over from the moment the file lands in that folder.

## Consequences

The MVP can be delivered without needing bank partnership negotiations or API access, which are outside the delivery team's control and timeline; the one remaining manual step (download + drop file) is small compared to the manual reconciliation work being eliminated. On the other hand, there is a residual manual step and its associated latency (finance still has to remember to download periodically); the system must defensively handle messy real-world file conditions (partial downloads, duplicate uploads, format drift) since it does not control the data source directly. Direct API integration can be reconsidered in Phase 3 if volume/economics justify it.
