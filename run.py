import os
from dotenv import load_dotenv
load_dotenv()

from database import (
    get_client,
    get_known_nit_numbers,
    upsert_tenders,
    get_all_profiles,
    get_unmatched_tenders,
    save_recommendation,
    mark_emailed,
)
from scraper import scrape_all
from embedder import embed_tenders, store_embeddings
from matcher import match_profile
from emailer import send_digest


def main():
    client = get_client()

    # Step 1 — Scrape new tenders
    print("=== Step 1: Scraping tenders ===")
    known = get_known_nit_numbers(client)
    print(f"  Known tenders in DB: {len(known)}")
    new_tenders = scrape_all(known_nit_numbers=known)
    inserted = upsert_tenders(client, new_tenders)
    print(f"  New tenders inserted: {inserted}")

    # Step 1b — Embed new tenders
    if new_tenders:
        print("  Embedding new tenders...")
        tenders_from_db = client.table("tenders").select("*").in_(
            "nit_number", [t.nit_number for t in new_tenders]
        ).execute().data
        pairs = embed_tenders(tenders_from_db)
        stored = store_embeddings(client, pairs)
        print(f"  Embeddings stored: {stored}")

    # Step 2 — Match and email each profile
    print("\n=== Step 2: Matching profiles ===")
    profiles = get_all_profiles(client)
    print(f"  Profiles found: {len(profiles)}")

    for profile in profiles:
        print(f"\n  Profile: {profile['name']} ({profile['email']})")

        scored = match_profile(client, profile)

        # Save all scored recommendations to DB
        for r in scored:
            save_recommendation(
                client,
                tender_id=r["tender_id"],
                profile_id=profile["id"],
                score=r["score"],
                reason=r["reason"],
            )

        # Send email only for recommendations scoring 5+
        if scored:
            # Fetch full tender details for email enrichment
            tender_ids = [r["tender_id"] for r in scored]
            tender_rows = client.table("tenders").select("*").in_("id", tender_ids).execute().data
            tender_map = {t["id"]: t for t in tender_rows}
            enriched = [
                {
                    "relevance_score": r["score"],
                    "relevance_reason": r["reason"],
                    "tender": tender_map[r["tender_id"]],
                }
                for r in scored
                if r["tender_id"] in tender_map
            ]
            enriched.sort(key=lambda x: x["relevance_score"], reverse=True)
            send_digest(enriched, profile)

            # Mark as emailed
            rec_ids = []
            for r in scored:
                result = (
                    client.table("recommendations")
                    .select("id")
                    .eq("tender_id", r["tender_id"])
                    .eq("profile_id", profile["id"])
                    .execute()
                )
                if result.data:
                    rec_ids.append(result.data[0]["id"])
            mark_emailed(client, rec_ids)
        else:
            print("  No relevant tenders found for this profile today.")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
