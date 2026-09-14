# ADR-0001: Record Architecture Decisions

## Status

Accepted

## Context

Throughout the planning process for this payment verification and reconciliation system, a number of significant architectural decisions have been made (choice of database as system of record, deterministic matching approach, finance-first delivery sequencing, teller data-capture mechanism, and others). These decisions have been scattered across various planning documents and conversations, with no standard format that makes them easy to find, reference later, or understand the reasoning behind (not just the outcome) for anyone who joins this project in the future -- including a possible replacement solo developer in a handover scenario.

## Decision

We will record architecture decisions using the Architecture Decision Record (ADR) format as defined by Michael Nygard, stored as sequentially numbered, append-only markdown files in the `docs/adr/` folder of the project repository. Each ADR contains four sections: Status, Context, Decision, and Consequences.

## Consequences

Anyone joining this project can see the reasoning behind past decisions and will not need to reopen settled discussions without new information. Decisions that later need to change or be reversed will be recorded as new ADRs that supersede the old ones -- not by editing or deleting the existing history. The practical consequence is that every subsequent major decision on this project should also be written up as a new ADR, not just discussed and then forgotten in format.
