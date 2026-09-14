# ADR-0003: Deterministic Rule-Based Matching, Not Machine Learning

## Status

Accepted

## Context

The system must match customer-side transaction claims against bank statement data. Possible approaches range from simple exact-field matching to fuzzy matching to a full machine learning model. Financial reconciliation errors have direct monetary and trust consequences, and stakeholders require a process that can be explained and audited. The organization also does not want an opaque AI model making money-movement decisions.

## Decision

We will implement a hierarchical, deterministic, rule-based matching engine (reference match -> reference+amount -> amount+name+bank+time window -> fuzzy name matching), producing an explicit numeric score with a threshold calibrated from historical data. Machine learning is not used to decide financial matches; ML may only be used later (Phase 3) to help prioritize the human review queue, always with a human in the loop for the final decision.

## Consequences

Every match outcome can be explained ("matched because reference X matched and amount matched within tolerance"); thresholds can be audited and re-tuned through standard software testing; conversations with auditors/regulators become simpler. On the other hand, the rule engine requires more explicit engineering effort per edge case (partial payment, many-to-many, missing reference) than "letting a model learn it"; the matching accuracy ceiling may be lower than a well-tuned ML model for complex edge cases, requiring ongoing manual review capacity.
