# ADR 0003: Nothing is ever sent automatically

Date: 2026-10-28
Status: Accepted (planned)

## Context

The core value of the product is automation, but applications sent on the
user's behalf without review are legally and reputationally risky, and
hallucinated letters must never reach an employer. The spec makes this the
hard rule.

## Decision

- Every application requires an explicit user action on a final confirmation
  dialog (recipient, subject, attachments) before any send.
- The default mode creates a draft in the user's mailbox; direct sending is
  opt-in per settings.
- No scheduler, batch job, or background process may ever trigger a send.
- The review screen is the single gateway to sending, and a grounding check
  flags unsupported claims before the user approves.

## Consequences

- There is exactly one code path to sending, guarded by user confirmation.
- Tests assert that no send path is reachable without the confirmation step.
- For application-form offers, the MVP only pre-fills/copies and opens the
  URL; no fragile full automation.
