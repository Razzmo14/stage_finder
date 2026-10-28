# Stage Finder — User Guide

Stage Finder is a local-first desktop application that automates job and
internship applications, assisted by an LLM, while you always keep the
final say before anything is sent.

**The hard rule: nothing is ever sent automatically.** Every send requires
an explicit confirmation on a final dialog, per application. By default the
app only creates a draft in your mailbox.

## First launch

1. Start the app (see `README.md` for installation/development).
2. The status bar at the bottom shows the sidecar health — it must be
   healthy for anything to work.

## Configure the LLM (Settings)

1. Create an OpenRouter account and an API key.
2. In **Settings → LLM (OpenRouter)**, paste the key and click
   *Save key*. The key is stored in your OS keychain only — never in a
   file or the database — and is displayed masked afterwards.
3. Pick a model from the live catalog (searchable) and use **Test** to
   verify the connection. Cost per request is recorded.
4. Optionally switch the provider (Anthropic, OpenAI, or a fully local
   Ollama server) and set a monthly budget cap. When the budget is
   exceeded, generation stops with a clear message.

## Your profile (Profile)

- Fill in your identity, skills, languages and summary manually, **or**
  import a CV (PDF/DOCX): the LLM extracts a structured draft that you
  can correct before saving.
- Write your base cover letter and set the tone, language and
  *never-say* rules.

## Search for offers (Search & Offers)

1. Save search criteria (keywords, location, radius, contract types,
   sources: France Travail, Adzuna, Jooble).
2. **Run search** fetches and normalizes offers; duplicates across runs
   and sources are removed (hash + fuzzy match).
3. **Run matching** scores the best offers 0-100 against your profile
   (embedding similarity, then LLM re-ranking with rationale, matched and
   missing skills, red flags). The list is sorted by score.
4. **Settings → Scheduled searches** can run searches periodically and
   remind you of follow-ups. The scheduler can never send anything.

## Review (Review queue)

For every generated letter you can:

- see the offer and the letter side by side, with a diff against your
  base letter;
- edit the letter inline and save;
- regenerate with instructions ("shorter", "more formal", ...) — the new
  text streams into the editor; you can also pick another model;
- check flagged claims: the grounding check highlights claims that are
  not supported by your profile. Fix or remove them before approving;
- choose **Approve** (intent only), **Save for later**, or **Reject**.

## Deliver to your mailbox

1. **Settings → Email (Gmail)**: connect your account (OAuth2). Outlook
   (Microsoft Graph) and generic SMTP/IMAP accounts are configured via
   the OS keychain (see `README.md`).
2. In the Review queue, an approved application offers **Deliver to
   Gmail...**: a final dialog summarizes the recipient, subject and
   attachments. Choose **Create draft** (default) or **Send directly**
   (only available if you enabled it in Settings) and confirm
   explicitly. A per-day send limit applies to direct sends.

## Track applications (Applications)

- Kanban view by status, list view, per-application timeline
  (generated, edited, approved, draft created, sent, ...).
- Follow-up dates are highlighted; due follow-ups trigger a desktop
  notification.

## Privacy

- All data stays on your machine except what is sent to your chosen LLM
  gateway and your email provider.
- OpenRouter routing defaults to `data_collection="deny"`.
- Secrets (API keys, OAuth tokens, SMTP passwords) live exclusively in
  the OS keychain.
- You can delete everything by removing the app data directory shown in
  the data dir of your platform (`~/.local/share/stage-finder` on Linux,
  `~/Library/Application Support/stage-finder` on macOS,
  `%LOCALAPPDATA%/stage-finder` on Windows).

## Language

Switch the interface between English and French in the sidebar
(settings are remembered).
