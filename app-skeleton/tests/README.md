# tests

- `unit/` -- tests for critical logic (formatter, scoring, normalization) with no external dependencies.
- `integration/` -- end-to-end tests against the database and local files (using the files in `samples/`).
- `fixtures/` -- copy files from `samples/` here if you need a modified version specifically for a test (do not modify the originals in `samples/`).

See Technical Design Document Section 27 (Testing Strategy) and Solo Delivery Plan Section 8 (Definition of Done) for the minimum coverage standard.
