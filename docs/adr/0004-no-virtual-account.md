# ADR-0004: Multi-Field Reconciliation Without a Virtual Account

## Status

Accepted

## Context

Some payment platforms rely on a per-customer Virtual Account (VA) issued by a bank to make reconciliation trivial (1 VA = 1 customer = unambiguous match). The company's Malaysia operation does not have VA infrastructure available, and building it out is a significant separate bank/partner integration project outside current scope.

## Decision

Reconciliation will be performed using a combination of transaction reference (when available), amount, sender name, bank, and timestamp proximity, through the hierarchical matching engine (ADR-0003) -- instead of relying on unambiguous VA-based identification.

## Consequences

The system can be built and shipped without needing new bank partnership/integration work, keeping the MVP achievable with the resources on hand. On the other hand, matching must handle inherent ambiguity (same amount from multiple different customers, missing reference, name-writing variation) that would not arise in a VA-based design; a non-zero manual review rate should be expected, which a VA-based design would not experience. The VA option can be reconsidered in Phase 3 if a bank partner offers it and transaction volume justifies the investment.
