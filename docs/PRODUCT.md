# Product Description -- Stage Finder

> Status: specification only. Nothing is implemented yet; the plan of record
> is `feature_list.json` (start at `skel-001`).

## What Is This?

Stage Finder is a local-first, cross-platform desktop application that
automates job and internship applications, assisted by an LLM, while the user
always keeps the final say before anything is sent.

The user stores a profile (CV, skills, experiences, education, languages,
preferences) and a base cover letter. The app searches job and internship
offers matching user-defined criteria, scores and ranks them against the
profile, and uses an LLM to adapt the cover letter (and optionally a short
email body) to each selected offer. A validation screen lets the user review,
edit, approve or reject each application. Nothing is ever sent automatically:
every send requires an explicit user click, per application. Every
application is tracked (status, dates, follow-ups, responses).

## HARD RULE

Nothing is ever sent automatically. Every send requires an explicit user
action on a final confirmation dialog, per application. Direct sending is
opt-in; the default mode creates a draft in the user's mailbox.

## Core Features

### Onboarding and profile
- Import a CV (PDF/DOCX), extract a structured profile via the LLM, let the
  user correct everything.
- Import or write a base cover letter; define tone, length, language, and
  "never say" rules.

### Offer search
- Saved criteria: keywords, location, radius, contract type, remote, salary,
  seniority, languages, sources, date posted, schedule.
- Manual and scheduled runs across all enabled sources.
- Normalization to a common Offer schema, deduplication across sources
  (hash + fuzzy match), filtering of already seen or ignored offers.

### Matching
- Stage 1: embedding similarity between the profile and the offer.
- Stage 2: LLM re-ranking returning a structured result: score 0-100, short
  rationale, matched skills, missing skills, red flags.
- Offers displayed sorted by score with filters.

### Letter adaptation
- Inputs: structured profile, base letter, offer text, user style rules.
- Output (structured): adapted letter, email subject, email body, list of
  claims made.
- Anti-hallucination: the prompt forbids inventing skills, experiences,
  degrees or facts; a verification step checks every factual claim against
  the profile; unsupported claims are flagged in the UI.
- French and English support, with offer language detection.

### Review and validation (critical)
- Side-by-side view: offer on one side, generated letter on the other, with
  a diff against the base letter.
- Inline editing, streamed regeneration with instructions ("shorter", "more
  formal", "emphasize project X"), attachments selection, regeneration with
  a different model.
- Flagged unsupported claims highlighted.
- Three actions: Approve and send, Save as draft in mailbox, Reject. Bulk
  review queue with keyboard shortcuts.
- A final confirmation dialog summarizing recipient, subject, attachments
  before any send.

### Sending
- OAuth2 (PKCE) connection to Gmail and Outlook, with SMTP/IMAP fallback.
- Per-day send limit (configurable), rate limiting, retry with backoff,
  clear error handling.
- For application-form offers: pre-fill what is possible, copy the letter to
  the clipboard, open the offer URL. No fragile full automation in the MVP.

### Tracking
- Kanban/list view of applications by status, timeline per application,
  follow-up reminders (desktop notifications), optional reply detection via
  the mailbox.

### Settings
- LLM configuration: OpenRouter API key (OS keychain only), searchable model
  picker from the live catalog, per-task model assignment, routing and
  privacy options, budget cap, local-only mode with Ollama.
- Embedding provider, email accounts, send limits, data export (JSON/CSV),
  full data deletion, language and theme.

## Technical Requirements

- Desktop shell: Tauri 2 (minimal Rust core: window lifecycle, sidecar
  management, a few commands, secure IPC).
- Frontend: React + TypeScript + Vite + Tailwind CSS + shadcn/ui; Zustand for
  UI state, TanStack Query for server state; React Router or TanStack Router.
- Local backend sidecar: Python 3.12 + FastAPI, launched and supervised by
  Tauri; uv for dependencies; Pydantic v2 for validation.
- Database: SQLite via SQLModel with Alembic migrations; sqlite-vec for
  embeddings.
- LLM: OpenRouter as the primary gateway (official OpenAI Python SDK pointed
  at base_url="https://openrouter.ai/api/v1"), thin LLMProvider interface
  with OpenRouter (default), direct Anthropic/OpenAI, and Ollama
  implementations. No LangChain; direct SDK calls only.
- Embeddings: pluggable, independent from the chat model (local
  sentence-transformers by default, or API-based), stored in sqlite-vec with
  the embedding model name.
- Job sources: official APIs first (France Travail "Offres d'emploi", Adzuna,
  Jooble) behind a JobSource plugin interface. No scraping of sites whose
  terms forbid it (e.g. LinkedIn, Indeed); Playwright only as an optional
  complement on allowed sites.
- Document parsing: PyMuPDF or pdfplumber for PDFs; LLM-based extraction into
  a structured profile.
- Document export: python-docx and WeasyPrint (PDF).
- Email: Gmail API and Microsoft Graph via OAuth2 (PKCE), plus generic
  SMTP/IMAP fallback. Default mode: create a draft in the mailbox.
- Secrets: OS keychain via keyring (and the Tauri OS keychain plugin). Never
  in plain text or in the database.
- Background jobs: APScheduler (periodic searches, follow-up reminders).
- Packaging: Python sidecar frozen with PyInstaller (or Nuitka), declared as
  externalBin in Tauri, one binary per OS/architecture; CI with GitHub
  Actions for Windows, macOS and Linux.
- Quality: ruff + mypy/pyright + pytest on the backend; ESLint + Prettier +
  Vitest on the frontend; pre-commit hooks.

## User Interface

The app opens on an overview of the pipeline: profile completeness, latest
searches, and applications awaiting review. Navigation is a sidebar
(Overview, Profile, Search & Offers, Review queue, Applications, Settings)
with a status bar (sidecar health, LLM model and estimated cost, language).

## Constraints

- All data stays local except what is sent to the chosen LLM gateway and the
  email provider; the UI shows exactly what is sent to the LLM.
- Localhost-only backend bound to 127.0.0.1 with a per-launch session token;
  every request must carry it.
- Respect each job source's terms of use and rate limits.
- GDPR by design: consent, data export, full deletion, privacy-preserving
  OpenRouter routing (data_collection="deny") by default.
- UI in French and English (i18next).
