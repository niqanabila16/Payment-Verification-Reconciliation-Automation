# ADR-0007: Automate the Finance Side Before Receipt OCR

## Status

Accepted (supersedes the original OCR-first sequencing in the initial Solo Delivery Plan)

## Context

The original solo delivery plan sequenced the Receipt OCR Pipeline as the first epic to be built, following the natural customer -> bank data flow. However, for delivery by a single person, OCR is the component with the highest uncertainty and steepest learning curve (image classification, extraction-accuracy tuning, external OCR-provider/WhatsApp Business API onboarding lead time), while the AS-IS pain point currently consuming the most ongoing labor sits on the finance side (manual bank-data download and matching), not on the teller side.

## Decision

We will build and ship finance-side automation (bank file ingestion, matching engine, exception handling) first, using a lightweight, non-OCR data-capture mechanism for the customer/teller side of the match (see ADR-0008), and defer the Receipt OCR Pipeline epic to Phase 2.

## Consequences

This removes OCR's technical risk and the WhatsApp Business API verification lead time from the critical path of the first release; it delivers value against the largest current pain point (finance's manual labor) the fastest; the teller/customer-facing workflow is unchanged in Phase 1, reducing change-management risk. On the other hand, the root cause of teller transcription error (manual receipt reading) is not addressed until Phase 2; there is a risk that organizational urgency to fund Phase 2 (OCR) decreases once the Phase 1 pain point is resolved -- mitigated by locking the Phase 2 scope and budget commitment at the same time Phase 1 is approved, rather than renegotiating it afterward.
