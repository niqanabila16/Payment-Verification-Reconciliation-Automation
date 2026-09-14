# app/formatter

Teller string generator -- a deterministic function that turns structured data into the `KJG/NAME/.../CHK` string format, and a parser for the reverse direction. See Technical Design Document Section 11 and `samples/sample_teller_strings.md` for input/output examples.

Logic here **must** have unit tests (see `tests/unit/`) since there is no peer review when working solo (see Solo Delivery Plan, Section 8 -- Definition of Done).
