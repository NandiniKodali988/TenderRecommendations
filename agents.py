import json
import os
import anthropic

MODEL = "claude-haiku-4-5-20251001"

TOOLS = [
    {
        "name": "run_scraper",
        "description": (
            "Scrape tenders.bhel.com for new BHEL tenders, store them in the database, "
            "and generate vector embeddings for semantic search. "
            "Returns the number of new tenders found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "run_analyst",
        "description": (
            "Run the RAG matching pipeline for a sub-contractor profile: "
            "vector similarity search in pgvector, keyword filtering, and Claude re-ranking. "
            "Saves scored results to the recommendations table. "
            "Returns the number of relevant tenders found for this profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "description": "UUID of the sub-contractor profile to run matching for.",
                }
            },
            "required": ["profile_id"],
        },
    },
    {
        "name": "run_editor",
        "description": (
            "Format and send the daily email digest for a sub-contractor profile "
            "based on recommendations already saved to the database. "
            "Only sends recommendations that have not yet been emailed. "
            "Returns whether the email was sent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "description": "UUID of the sub-contractor profile to send the digest for.",
                }
            },
            "required": ["profile_id"],
        },
    },
]


# --- Tool implementations ---

def _tool_run_scraper(db_client) -> dict:
    from scraper import scrape_all
    from database import get_known_nit_numbers, upsert_tenders
    from embedder import embed_tenders, store_embeddings

    known = get_known_nit_numbers(db_client)
    new_tenders = scrape_all(known_nit_numbers=known)
    inserted = upsert_tenders(db_client, new_tenders)

    if new_tenders:
        tenders_from_db = (
            db_client.table("tenders")
            .select("*")
            .in_("nit_number", [t.nit_number for t in new_tenders])
            .execute()
            .data
        )
        pairs = embed_tenders(tenders_from_db)
        store_embeddings(db_client, pairs)

    return {"new_tenders": inserted}


def _tool_run_analyst(db_client, profile_id: str, profiles: list[dict]) -> dict:
    from matcher import match_profile
    from database import save_recommendation

    profile = next((p for p in profiles if p["id"] == profile_id), None)
    if not profile:
        return {"error": f"Profile {profile_id} not found", "recommendations": 0}

    scored = match_profile(db_client, profile)
    for r in scored:
        save_recommendation(
            db_client,
            tender_id=r["tender_id"],
            profile_id=profile_id,
            score=r["score"],
            reason=r["reason"],
        )
    return {"profile": profile["name"], "recommendations": len(scored)}


def _tool_run_editor(db_client, profile_id: str, profiles: list[dict]) -> dict:
    from emailer import send_digest
    from database import mark_emailed

    profile = next((p for p in profiles if p["id"] == profile_id), None)
    if not profile:
        return {"error": f"Profile {profile_id} not found", "sent": False}

    recs = (
        db_client.table("recommendations")
        .select("*, tenders(*)")
        .eq("profile_id", profile_id)
        .is_("emailed_at", "null")
        .gte("relevance_score", 5)
        .order("relevance_score", desc=True)
        .execute()
        .data
    )

    if not recs:
        return {"sent": False, "reason": "no new recommendations to send"}

    enriched = [
        {
            "relevance_score": r["relevance_score"],
            "relevance_reason": r["relevance_reason"],
            "tender": r["tenders"],
        }
        for r in recs
    ]
    send_digest(enriched, profile)
    mark_emailed(db_client, [r["id"] for r in recs])

    return {"sent": True, "digests_sent": len(enriched)}


def _execute_tool(name: str, tool_input: dict, db_client, profiles: list[dict]) -> dict:
    if name == "run_scraper":
        return _tool_run_scraper(db_client)
    elif name == "run_analyst":
        return _tool_run_analyst(db_client, tool_input["profile_id"], profiles)
    elif name == "run_editor":
        return _tool_run_editor(db_client, tool_input["profile_id"], profiles)
    return {"error": f"Unknown tool: {name}"}


# --- Orchestrator ---

def run_pipeline(db_client, profiles: list[dict]) -> None:
    """
    Multi-agent orchestrator: Claude drives the full pipeline via tool calls.

    Agents:
      ScraperAgent  — fetches and embeds new tenders
      AnalystAgent  — RAG matching + re-ranking per profile
      EditorAgent   — formats and sends email digest per profile
    """
    if not profiles:
        print("  No profiles found, nothing to do.")
        return

    profile_summary = "; ".join(
        f"{p['name']} (id={p['id']})" for p in profiles
    )

    anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    messages = [
        {
            "role": "user",
            "content": (
                "Run the daily BHEL tender digest pipeline. "
                f"Profiles to process: {profile_summary}. "
                "Steps in order: "
                "1) Call run_scraper once to fetch and embed new tenders. "
                "2) Call run_analyst for each profile. "
                "3) Call run_editor for each profile to send email digests."
            ),
        }
    ]

    print("  Orchestrator starting agentic loop...")

    while True:
        response = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        for block in response.content:
            if hasattr(block, "text") and block.text:
                print(f"  Orchestrator: {block.text}")

        if response.stop_reason == "end_turn":
            print("  Orchestrator finished.")
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  → [{block.name}] input={json.dumps(block.input)}")
                    result = _execute_tool(block.name, block.input, db_client, profiles)
                    print(f"    ← result={json.dumps(result)}")
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
