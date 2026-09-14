# ADR-0006: Internal Finance Notifications via Microsoft Teams, Not WhatsApp Group Automation

## Status

Accepted

## Context

The current process posts teller-typed transaction strings into a WhatsApp group used by finance. The official WhatsApp Business Platform API is designed for business-to-customer messaging (1:1 or template broadcast), not for posting into an existing internal WhatsApp group; doing so would require unofficial, ToS-violating tooling, which is unacceptable for a system handling financial data. The company already operates within a Microsoft 365 environment.

## Decision

Customer-facing communication will continue to use the WhatsApp Business Platform (its intended use case). Internal finance notifications (new exceptions, review-queue alerts, etc.) will use Microsoft Teams instead of the WhatsApp group, since Teams is natively governed by the company's Microsoft tenant security controls (Conditional Access, audit log).

## Consequences

There is no longer any dependency on unofficial/unsupported WhatsApp automation; the notification audit trail becomes native to the Microsoft tenant that is already governed by the security team. On the other hand, finance staff must adopt a new notification channel (Teams) in place of the WhatsApp group they have used for internal coordination; setting up and governing a Teams channel/webhook becomes part of the delivery scope.
