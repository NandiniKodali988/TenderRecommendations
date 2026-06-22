# TenderRecommendations

## What this project does

A tender recommendation platform for sub-contractors working with BHEL (Bharat Heavy Electricals Limited). BHEL posts tenders on the GeM (Government e-Marketplace) portal but only emails sub-contractors about some of them. This system monitors all BHEL tenders daily, matches them against a sub-contractor's work scope using AI, and delivers a personalised digest every morning.

## Current scope

Multi-user. Each sub-contractor has their own profile and sees only their own recommendations. Built and deployed publicly on Hugging Face Spaces.

## Build status — complete and working

**Core pipeline:**
- `scraper.py` — scrapes tenders.bhel.com, early-stop on known tenders
- `database.py` — Supabase service-role client (upsert tenders, read profiles, save recommendations, feedback)
- `embedder.py` — sentence-transformers (all-MiniLM-L6-v2) embeddings + pgvector similarity search
- `matcher.py` — hard filter (location, type, keywords) + RAG (pgvector) + Claude Haiku scoring + feedback-weighted query vector
- `emailer.py` — Gmail SMTP HTML digest
- `run.py` — orchestrates full pipeline
- `agents.py` — multi-agent architecture using Claude tool use (orchestrator, scraper, analyst, editor agents)
- `api.py` — FastAPI REST API (profiles, recommendations, feedback endpoints)
- `app.py` — Streamlit dashboard (Google OAuth, profile setup, recommendations, thumbs up/down feedback, on-demand refresh button)
- `.github/workflows/daily.yml` — GitHub Actions cron at 8 AM IST
- `.github/workflows/ci.yml` — CI runs pytest on every push and pull request

**Evaluation:**
- `eval/export.py` — exports a profile's recommendations + human feedback to JSON
- `eval/llm_judge.py` — independent LLM judge re-scores each tender, compares with original Claude scores and human feedback, prints agreement summary

**Tests:**
- `tests/test_matcher.py` — 12 unit tests for keyword filter and feedback weight logic
- `tests/test_api.py` — 7 unit tests for FastAPI endpoints (health, feedback, profiles)
- `requirements-dev.txt` — pytest + httpx

**SQL:**
- `sql/schema.sql` — base schema (tenders, profiles, recommendations)
- `sql/schema_phase2.sql` — adds embedding column to tenders
- `sql/schema_phase2_rpc.sql` — pgvector RPC functions for similarity search
- `sql/schema_rls.sql` — Row Level Security policies

## Architecture

```
Daily scrape (GitHub Actions cron — 8 AM IST)
  → scraper.py fetches ALL active BHEL tenders from tenders.bhel.com
  → upsert into Supabase tenders table (early-stop when known tenders hit)

For each sub-contractor profile:
  → Step 1 — Hard filter (no API cost):
      location, tender type, keywords include/exclude
  → Step 2 — RAG (pgvector):
      embed remaining tenders with sentence-transformers
      blend liked tender embeddings into query vector (feedback boost)
      similarity search retrieves top-K candidates
  → Step 3 — Claude Haiku scoring:
      score each candidate 1-10 against work scope
      attach plain-English match reason
  → Step 4 — Email digest:
      ranked list of relevant tenders with title, deadline, link, reason

Web app (Streamlit on Hugging Face Spaces via Docker)
  → Google OAuth login via Supabase Auth + PKCE flow
  → Sub-contractor sets profile: locations, tender types, work scope, keywords
  → View recommendations with relevance score and match reason
  → Thumbs up/down feedback stored in Supabase, improves future recommendations
  → "Refresh recommendations" button clears stale recs and re-runs matcher on demand
  → Row Level Security: each user only sees their own data

FastAPI (api.py)
  → REST endpoints: GET/POST/PUT profiles, GET recommendations, POST feedback
  → Supabase service-role client, no RLS bypass needed for pipeline
```

## Key design principle

The scraper fetches broadly and is profile-agnostic. Filters live in the profile, not the scraper. Adding a new user requires zero changes to the pipeline.

## Tech stack

| Component | Tool |
|---|---|
| Web app | Streamlit, hosted on Hugging Face Spaces (Docker) |
| REST API | FastAPI |
| Database + auth | Supabase (PostgreSQL + pgvector + Supabase Auth + RLS) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| AI scoring + agents | Claude Haiku (Anthropic API) |
| Email | Gmail SMTP |
| Scheduling | GitHub Actions cron |
| Tests | pytest, 19 unit tests, CI on every push |
| Deployment | Docker, Hugging Face Spaces |

## Credentials

Stored as GitHub Actions secrets and Hugging Face Space secrets:
- `SUPABASE_URL` and `SUPABASE_KEY` (service role) — pipeline + on-demand matching
- `SUPABASE_ANON_KEY` — Streamlit app (enforces RLS)
- `ANTHROPIC_API_KEY` — Claude Haiku scoring
- `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` — email digest
- `APP_URL` — Hugging Face Space URL (used for OAuth redirect)

## Key constraints

- Keep all external service usage within free tiers
- Claude API calls only for genuinely new tenders (not re-scored on every run)
- Scraper is respectful: delays between requests, early-stop on known tenders
- PKCE verifier stored server-side in `@st.cache_resource` (single-user safe; for multi-user production, key by session ID)
- Fresh Supabase client created per request to avoid HTTP/2 connection drops on HF Spaces
