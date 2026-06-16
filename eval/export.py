"""
Export a profile's recommendations to JSON for evaluation.

Usage:
    python -m eval.export                        # export all profiles
    python -m eval.export user@example.com       # export one profile by email
    python -m eval.export user@example.com out.json  # custom output path
"""

import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from database import get_client

OUTPUT_PATH = "eval/eval_dataset.json"


def export(email: str | None = None, output_path: str = OUTPUT_PATH) -> None:
    client = get_client()

    if email:
        result = client.table("profiles").select("*").eq("email", email).execute()
    else:
        result = client.table("profiles").select("*").execute()

    profiles = result.data
    if not profiles:
        print("No profiles found.")
        return

    dataset = []
    for profile in profiles:
        recs_result = (
            client.table("recommendations")
            .select("*, tenders(*)")
            .eq("profile_id", profile["id"])
            .order("relevance_score", desc=True)
            .execute()
        )

        recommendations = []
        for rec in recs_result.data:
            t = rec.get("tenders") or {}
            recommendations.append({
                "recommendation_id": rec["id"],
                "tender_id": rec["tender_id"],
                "tender_title": t.get("title", ""),
                "tender_unit": t.get("unit", ""),
                "tender_ref": t.get("notification_number", ""),
                "tender_url": t.get("detail_url", ""),
                "is_gem": t.get("is_gem", False),
                "claude_score": rec["relevance_score"],
                "claude_reason": rec["relevance_reason"],
                "human_feedback": rec.get("feedback"),  # 1 = helpful, -1 = not helpful, None = no rating
                "llm_judge_score": None,
                "llm_judge_reason": None,
            })

        dataset.append({
            "profile": {
                "id": profile["id"],
                "email": profile["email"],
                "work_scope": profile["work_scope"],
                "preferred_units": profile.get("preferred_units", []),
                "gem_only": profile.get("gem_only", True),
                "preferred_tender_types": profile.get("preferred_tender_types", []),
                "include_keywords": profile.get("include_keywords", []),
                "exclude_keywords": profile.get("exclude_keywords", []),
            },
            "recommendations": recommendations,
        })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(dataset, f, indent=2, default=str)

    total = sum(len(d["recommendations"]) for d in dataset)
    print(f"Exported {len(dataset)} profile(s), {total} recommendation(s) → {output_path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    export(
        email=args[0] if len(args) >= 1 else None,
        output_path=args[1] if len(args) >= 2 else OUTPUT_PATH,
    )
