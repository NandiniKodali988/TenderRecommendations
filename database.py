import os
from dataclasses import asdict
from supabase import create_client, Client
from scraper import Tender

def get_client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def get_known_nit_numbers(client: Client) -> set[str]:
    """Return all NIT numbers already in the database (for early-stop scraping)."""
    result = client.table("tenders").select("nit_number").execute()
    return {row["nit_number"] for row in result.data}


def upsert_tenders(client: Client, tenders: list[Tender]) -> int:
    """Insert new tenders, skip duplicates. Returns count of inserted rows."""
    if not tenders:
        return 0
    rows = [asdict(t) for t in tenders]
    result = (
        client.table("tenders")
        .upsert(rows, on_conflict="nit_number", ignore_duplicates=True)
        .execute()
    )
    return len(result.data)


def get_all_profiles(client: Client) -> list[dict]:
    result = client.table("profiles").select("*").execute()
    return result.data


def save_recommendation(
    client: Client,
    tender_id: str,
    profile_id: str,
    score: int,
    reason: str,
) -> None:
    client.table("recommendations").upsert(
        {
            "tender_id": tender_id,
            "profile_id": profile_id,
            "relevance_score": score,
            "relevance_reason": reason,
        },
        on_conflict="tender_id,profile_id",
    ).execute()


def get_unmatched_tenders(client: Client, profile_id: str) -> list[dict]:
    """Return tenders not yet matched against this profile."""
    already_matched = (
        client.table("recommendations")
        .select("tender_id")
        .eq("profile_id", profile_id)
        .execute()
    )
    matched_ids = {row["tender_id"] for row in already_matched.data}

    all_tenders = client.table("tenders").select("*").execute()
    return [t for t in all_tenders.data if t["id"] not in matched_ids]


def mark_emailed(client: Client, recommendation_ids: list[str]) -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for rec_id in recommendation_ids:
        client.table("recommendations").update({"emailed_at": now}).eq("id", rec_id).execute()


def save_feedback(client: Client, rec_id: str, value: int) -> None:
    """Store thumbs up (1) or thumbs down (-1) for a recommendation."""
    client.table("recommendations").update({"feedback": value}).eq("id", rec_id).execute()


def get_liked_tender_embeddings(client: Client, profile_id: str) -> list[list[float]]:
    """Return embeddings of tenders the user rated helpful (feedback=1)."""
    import json
    recs = (
        client.table("recommendations")
        .select("tender_id")
        .eq("profile_id", profile_id)
        .eq("feedback", 1)
        .execute()
    )
    if not recs.data:
        return []
    tender_ids = [r["tender_id"] for r in recs.data]
    tenders = client.table("tenders").select("embedding").in_("id", tender_ids).execute()
    vectors = []
    for t in tenders.data:
        raw = t.get("embedding")
        if raw:
            vectors.append(json.loads(raw) if isinstance(raw, str) else raw)
    return vectors
