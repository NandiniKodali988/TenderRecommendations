import json
import os
import numpy as np
import anthropic
from embedder import embed_query, find_similar_tenders
from database import get_liked_tender_embeddings

MODEL = "claude-haiku-4-5-20251001"
TOP_K = 20  # number of candidates to retrieve via vector search before Claude re-ranks
MAX_FEEDBACK_WEIGHT = 0.3  # feedback signal caps at 30% of the query vector blend


def keyword_filter(tenders: list[dict], profile: dict) -> list[dict]:
    """
    Apply keyword include/exclude filters after vector search.
    Location and GeM filters are handled server-side in find_similar_tenders.
    """
    results = tenders

    include_keywords = profile.get("include_keywords") or []
    if include_keywords:
        results = [
            t for t in results
            if any(kw.lower() in (t.get("title") or "").lower() for kw in include_keywords)
        ]

    exclude_keywords = profile.get("exclude_keywords") or []
    if exclude_keywords:
        results = [
            t for t in results
            if not any(kw.lower() in (t.get("title") or "").lower() for kw in exclude_keywords)
        ]

    return results


def rerank_with_claude(tenders: list[dict], profile: dict) -> list[dict]:
    """
    Re-rank vector search candidates with Claude Haiku.
    Returns list of {tender_id, score, reason} for score >= 5.
    """
    if not tenders:
        return []

    work_scope = profile.get("work_scope") or "General construction and procurement"

    tender_list = "\n".join(
        f"{i+1}. [ID: {t['id']}] {t['title']} | Unit: {t['unit']} | "
        f"Vector similarity: {t.get('similarity', 0):.2f}"
        for i, t in enumerate(tenders)
    )

    prompt = f"""You are helping a sub-contractor find relevant BHEL tenders to bid on.

Sub-contractor's work scope:
{work_scope}

These tenders were pre-selected by semantic similarity search as potentially relevant.
Score each on a scale of 1-10 for relevance to the work scope, and give a one-sentence reason.
Only include tenders scoring 5 or above.

Tenders:
{tender_list}

Respond in JSON only:
[
  {{"tender_id": "<id>", "score": <1-10>, "reason": "<one sentence>"}},
  ...
]

If none score 5 or above, return: []"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw.strip())


def _feedback_boost_vector(client, profile_id: str) -> tuple[list[float], int] | tuple[None, int]:
    """
    Average the embeddings of tenders the user liked, then normalize.
    Returns (normalized_vector, count) so the caller can compute a dynamic weight.
    Returns (None, 0) if no positive feedback exists yet.
    """
    vectors = get_liked_tender_embeddings(client, profile_id)
    if not vectors:
        return None, 0
    avg = np.mean([np.array(v) for v in vectors], axis=0)
    norm = np.linalg.norm(avg)
    return ((avg / norm).tolist() if norm > 0 else None), len(vectors)


def match_profile(client, profile: dict) -> list[dict]:
    """
    RAG matching pipeline for one profile:
    1. Embed the profile's work scope
    2. Vector similarity search in pgvector (filtered by unit/GeM server-side)
    3. Keyword include/exclude filter
    4. Claude re-ranks the top candidates
    Returns scored results ready to save as recommendations.
    """
    work_scope = profile.get("work_scope") or ""
    if not work_scope:
        print("  No work scope set, skipping.")
        return []

    # Step 1 — embed the query
    print("  Embedding work scope...")
    query_vec = embed_query(work_scope)

    # Step 1b — blend with feedback signal if the user has liked tenders before.
    # Weight grows with each liked tender (0.03 per like), capping at MAX_FEEDBACK_WEIGHT.
    # This avoids a cold-start problem where 1-2 early likes dominate the query.
    boost_vec, liked_count = _feedback_boost_vector(client, profile["id"])
    if boost_vec:
        feedback_weight = min(MAX_FEEDBACK_WEIGHT, liked_count * 0.03)
        blended = (1 - feedback_weight) * np.array(query_vec) + feedback_weight * np.array(boost_vec)
        norm = np.linalg.norm(blended)
        query_vec = (blended / norm).tolist() if norm > 0 else query_vec
        print(f"  Query boosted with feedback signal ({liked_count} likes, weight={feedback_weight:.2f})")

    # Step 2 — vector search (location + GeM filter applied server-side)
    candidates = find_similar_tenders(
        client=client,
        query_embedding=query_vec,
        top_k=TOP_K,
        only_gem=profile.get("gem_only", False),
        preferred_units=profile.get("preferred_units") or [],
    )
    print(f"  Vector search returned: {len(candidates)} candidates")

    if not candidates:
        print("  No candidates from vector search.")
        return []

    # Step 3 — keyword filters
    candidates = keyword_filter(candidates, profile)
    print(f"  After keyword filter: {len(candidates)}")

    if not candidates:
        print("  Nothing passed keyword filter.")
        return []

    # Step 4 — Claude re-ranks
    scored = rerank_with_claude(candidates, profile)
    print(f"  Claude selected {len(scored)} as relevant (score >= 5)")

    return scored


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from database import get_client

    client = get_client()

    sample_profile = {
        "id": "test-profile-001",
        "name": "Test Sub-Contractor",
        "work_scope": (
            "Civil construction, structural fabrication, erection and commissioning "
            "of industrial equipment, boiler and turbine installation, mechanical works "
            "for power plants."
        ),
        "preferred_units": ["BHEL, Hyderabad", "BHEL, Trichy", "BHEL, Haridwar"],
        "gem_only": True,
        "include_keywords": [],
        "exclude_keywords": [],
    }

    print(f"Running RAG matcher for: {sample_profile['name']}")
    print(f"Work scope: {sample_profile['work_scope'][:80]}...\n")

    results = match_profile(client, sample_profile)

    print("\n--- Recommendations ---")
    for r in results:
        print(f"  Score {r['score']}/10 — tender_id: {r['tender_id']}")
        print(f"  Reason: {r['reason']}")
        print()
