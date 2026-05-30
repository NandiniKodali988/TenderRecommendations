import json
import os
import anthropic

MODEL = "claude-haiku-4-5-20251001"


def hard_filter(tenders: list[dict], profile: dict) -> list[dict]:
    """
    Apply the profile's preference filters before sending anything to Claude.
    Each filter only runs if the profile has set that preference.
    """
    results = tenders

    # Location filter
    preferred_units = profile.get("preferred_units") or []
    if preferred_units:
        results = [t for t in results if t["unit"] in preferred_units]

    # GeM-only filter
    if profile.get("gem_only"):
        results = [t for t in results if t.get("is_gem")]

    # Tender type filter — title-based keyword match since we don't scrape type yet
    preferred_types = profile.get("preferred_tender_types") or []
    if preferred_types:
        results = [
            t for t in results
            if any(pt.lower() in (t.get("title") or "").lower() for pt in preferred_types)
        ]

    # Keyword inclusion filter
    include_keywords = profile.get("include_keywords") or []
    if include_keywords:
        results = [
            t for t in results
            if any(kw.lower() in (t.get("title") or "").lower() for kw in include_keywords)
        ]

    # Keyword exclusion filter
    exclude_keywords = profile.get("exclude_keywords") or []
    if exclude_keywords:
        results = [
            t for t in results
            if not any(kw.lower() in (t.get("title") or "").lower() for kw in exclude_keywords)
        ]

    return results


def score_tenders_with_claude(tenders: list[dict], profile: dict) -> list[dict]:
    """
    Send all shortlisted tenders to Claude Haiku in a single call.
    Returns list of {tender_id, score, reason} dicts for score >= 5.
    """
    if not tenders:
        return []

    work_scope = profile.get("work_scope") or "General construction and procurement"

    tender_list = "\n".join(
        f"{i+1}. [ID: {t['id']}] {t['title']} | Unit: {t['unit']} | Opening: {t['opening_date']}"
        for i, t in enumerate(tenders)
    )

    prompt = f"""You are helping a sub-contractor find relevant BHEL tenders to bid on.

Sub-contractor's work scope:
{work_scope}

Below are BHEL tenders. For each one, score its relevance to the sub-contractor's work scope on a scale of 1-10, and give a one-sentence reason.

Only include tenders with a score of 5 or above in your response.

Tenders:
{tender_list}

Respond in JSON only, as an array of objects with this structure:
[
  {{"tender_id": "<id>", "score": <1-10>, "reason": "<one sentence>"}},
  ...
]

If no tenders score 5 or above, return an empty array: []"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


def match_profile(tenders: list[dict], profile: dict) -> list[dict]:
    """
    Full matching pipeline for one profile:
    1. Hard filter by preferences
    2. Claude semantic scoring
    Returns scored results ready to save as recommendations.
    """
    print(f"  Total tenders to consider: {len(tenders)}")

    shortlisted = hard_filter(tenders, profile)
    print(f"  After hard filter: {len(shortlisted)}")

    if not shortlisted:
        print("  Nothing passed the hard filter.")
        return []

    scored = score_tenders_with_claude(shortlisted, profile)
    print(f"  Claude scored {len(scored)} as relevant (score >= 5)")

    return scored


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from database import get_client

    client = get_client()
    tenders = client.table("tenders").select("*").execute().data
    print(f"Loaded {len(tenders)} tenders from Supabase\n")

    sample_profile = {
        "id": "test-profile-001",
        "name": "Test Sub-Contractor",
        "email": "test@example.com",
        "work_scope": (
            "Civil construction, structural fabrication, erection and commissioning "
            "of industrial equipment, boiler and turbine installation, mechanical works "
            "for power plants."
        ),
        "preferred_units": ["BHEL, Hyderabad", "BHEL, Trichy", "BHEL, Haridwar"],
        "gem_only": True,
        "preferred_tender_types": [],
        "include_keywords": [],
        "exclude_keywords": [],
    }

    print(f"Running matcher for: {sample_profile['name']}")
    print(f"Work scope: {sample_profile['work_scope'][:80]}...\n")

    results = match_profile(tenders, sample_profile)

    print("\n--- Recommendations ---")
    for r in results:
        tender = next(t for t in tenders if t["id"] == r["tender_id"])
        print(f"  Score {r['score']}/10 — {tender['title']}")
        print(f"  Reason: {r['reason']}")
        print(f"  Unit: {tender['unit']} | Opening: {tender['opening_date']}")
        print()
