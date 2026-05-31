# TenderRecommendations

## What this project does

A tender recommendation platform for sub-contractors working with BHEL (Bharat Heavy Electricals Limited). BHEL posts tenders on the GeM (Government e-Marketplace) portal but only emails sub-contractors about some of them. This system monitors all BHEL tenders on GeM, matches them against a sub-contractor's work scope using AI, and delivers a personalized daily digest.

## Current scope

Single sub-contractor to start. Built for public hosting. Expand to multiple users later.

## Build status

Phase 1 (core pipeline) — **complete and working:**
- `scraper.py` — scrapes tenders.bhel.com, early-stop on known tenders
- `database.py` — Supabase client (upsert tenders, read profiles, save recommendations)
- `matcher.py` — hard filter + Claude Haiku batch scoring
- `emailer.py` — Gmail SMTP HTML digest
- `run.py` — orchestrates full pipeline
- `app.py` — Streamlit profile setup + recommendations dashboard
- `.github/workflows/daily.yml` — GitHub Actions cron at 8 AM IST

Phase 2 (portfolio enhancements) — **planned, build in this order:**
1. RAG pipeline with pgvector
2. User feedback loop
3. Multi-agent architecture
4. FastAPI backend
5. Multi-user with Supabase Auth

## Architecture

```
Daily scrape (GitHub Actions cron)
  → Fetch ALL active BHEL tenders from tenders.bhel.com (no location filter)
  → Store new ones in Supabase (skip already-seen tenders)

For each sub-contractor profile:
  → Step 1 — Hard filter (applied in code, no API cost):
      - Location: only tenders from user's selected BHEL units
      - Source: GeM only (ref starts with GEM/) or all
      - Tender type: user's selected types (Work Contract, Supply, etc.)
      - Value range: min/max if set
  → Step 2 — Semantic match (Claude Haiku):
      - Score each shortlisted tender against user's work scope description
      - Attach a plain-English reason for the match
  → Step 3 — Email digest:
      - Send ranked list of relevant tenders with title, deadline, GeM link, match reason

Web app (Streamlit on Streamlit Community Cloud)
  → Sub-contractor sets profile once:
      - Preferred BHEL locations (multi-select)
      - Source preference: GeM only or all
      - Tender types (multi-select)
      - Work scope description (free text — what their company does)
      - Value range (optional)
      - Keywords to include / exclude (optional)
  → Can view past recommendations and their status
```

## Key design principle

The scraper fetches broadly and is profile-agnostic. Filters live in the profile, not the scraper. This means adding a new user later requires zero changes to the scraper — each profile independently filters and scores the same tender data.

## Tech stack

### Phase 1 (current, all free tier)

| Component | Tool |
|---|---|
| Web interface | Streamlit, hosted on Streamlit Community Cloud |
| Database | Supabase (PostgreSQL, free tier) |
| Scraper + matching | Python, runs in GitHub Actions |
| Matching engine | Claude Haiku API (~$0.003/day for ~20 tenders) |
| Email digest | Gmail SMTP |
| Scheduling | GitHub Actions cron (daily, every morning) |

### Phase 2 (planned enhancements)

| Component | Tool | Why |
|---|---|---|
| Vector embeddings | `sentence-transformers` (all-MiniLM-L6-v2) | Free, runs in GitHub Actions, no API cost |
| Vector store | Supabase pgvector | Already in Supabase, no new service needed |
| RAG pipeline | pgvector similarity search → Claude re-ranking | Most in-demand AI skill; replaces basic prompt matching |
| Feedback loop | Thumbs up/down in Streamlit → stored in Supabase | Turns static AI into adaptive AI |
| Multi-agent | Claude tool use — scraper / analyst / editor agents | Agentic AI architecture, very current |
| REST API | FastAPI | Separates backend from UI; reusable by other clients |
| Auth + multi-user | Supabase Auth (Google login) + Row Level Security | Makes it a real multi-tenant SaaS product |
| Extra data sources | bidplus.gem.gov.in + eprocurebhel.co.in | Broader coverage, shows data pipeline engineering |

## Data sources

- Primary: tenders.bhel.com/tenders — BHEL's official tender page, surfaces GeM reference numbers (format: GEM/2026/B/XXXXXXX), publicly accessible, no login or CAPTCHA
- Secondary (future): bidplus.gem.gov.in/advance-search — GeM's own portal, harder to scrape

## Database schema (planned)

Three tables in Supabase:
- `tenders` — scraped tender records (id, title, reference_number, category, division, value, deadline, description, gem_link, scraped_at)
- `profiles` — sub-contractor profile (id, name, email, work_categories, preferred_divisions, min_value, max_value, keywords)
- `recommendations` — match results (id, tender_id, profile_id, relevance_score, relevance_reason, emailed_at)

## Build order

### Phase 1 (complete)
1. ~~Scraper — fetch and parse tenders.bhel.com~~
2. ~~Database schema — tenders, profiles, recommendations tables~~
3. ~~Matching engine — Claude Haiku batch scoring~~
4. ~~Email digest — Gmail SMTP~~
5. ~~GitHub Actions cron workflow~~
6. ~~Streamlit app — profile setup + recommendations dashboard~~

### Phase 2 (next)
7. RAG pipeline — embed tenders with sentence-transformers, store in pgvector, semantic search before Claude scoring
8. Feedback loop — thumbs up/down in UI feeds back into scoring weights
9. Multi-agent — Claude tool use for scraper / analyst / editor agents
10. FastAPI backend — REST API layer, Streamlit becomes a thin client
11. Multi-user + auth — Supabase Auth, RLS, each user sees only their data

## Credentials needed (stored as GitHub Actions secrets + Streamlit secrets)

- `SUPABASE_URL` and `SUPABASE_KEY` — from Supabase project settings
- `ANTHROPIC_API_KEY` — Claude Haiku, pay-as-you-go
- `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` — Gmail SMTP sender

## Key constraints

- Keep all external service usage within free tiers
- Claude API calls should only happen for genuinely new tenders (not re-scored on every run)
- Scraper should be respectful: add delays, avoid hammering the server
