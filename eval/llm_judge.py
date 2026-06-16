"""
Re-score recommendations with an independent LLM judge and compare to the original
Claude scores and any human feedback already collected.

Usage:
    python -m eval.llm_judge                       # reads eval/eval_dataset.json
    python -m eval.llm_judge path/to/dataset.json  # custom path

The script writes llm_judge_score and llm_judge_reason into the same JSON file,
then prints an agreement summary.
"""

import json
import sys

import anthropic
from dotenv import load_dotenv
load_dotenv()

DATASET_PATH = "eval/eval_dataset.json"

JUDGE_PROMPT = """\
You are an independent evaluator assessing whether a government tender is relevant \
to a sub-contractor's work scope.

Sub-contractor work scope:
{work_scope}

Tender title: {title}
BHEL unit posting this tender: {unit}

Rate how relevant this tender is to the sub-contractor on a scale from 1 to 10.
1 = completely irrelevant, 10 = perfect match.

Reply in exactly this format (no extra text):
SCORE: <integer 1-10>
REASON: <one sentence explaining your rating>"""


def _parse_response(text: str) -> tuple[int | None, str]:
    score = None
    reason = ""
    for line in text.strip().splitlines():
        if line.startswith("SCORE:"):
            try:
                score = int(line.replace("SCORE:", "").strip())
            except ValueError:
                pass
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()
    return score, reason


def run(dataset_path: str = DATASET_PATH) -> None:
    with open(dataset_path) as f:
        dataset = json.load(f)

    ai = anthropic.Anthropic()

    for entry in dataset:
        profile = entry["profile"]
        recs = entry["recommendations"]
        print(f"\nProfile: {profile['email']}  ({len(recs)} recommendations)")

        for rec in recs:
            prompt = JUDGE_PROMPT.format(
                work_scope=profile["work_scope"],
                title=rec["tender_title"],
                unit=rec["tender_unit"],
            )
            response = ai.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            judge_score, judge_reason = _parse_response(response.content[0].text)

            rec["llm_judge_score"] = judge_score
            rec["llm_judge_reason"] = judge_reason

            orig = rec["claude_score"]
            agree = (
                "✓" if orig is not None and judge_score is not None and abs(orig - judge_score) <= 2
                else "✗"
            )
            human = rec.get("human_feedback")
            human_str = " | human: 👍" if human == 1 else " | human: 👎" if human == -1 else ""
            print(f"  {agree}  original={orig}/10  judge={judge_score}/10{human_str}  {rec['tender_title'][:55]}")

    with open(dataset_path, "w") as f:
        json.dump(dataset, f, indent=2, default=str)

    _print_summary(dataset)
    print(f"\nResults saved → {dataset_path}")


def _print_summary(dataset: list[dict]) -> None:
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    for entry in dataset:
        profile = entry["profile"]
        recs = entry["recommendations"]
        print(f"\n{profile['email']}")

        # Claude vs LLM judge agreement
        scored = [r for r in recs if r["claude_score"] is not None and r["llm_judge_score"] is not None]
        if scored:
            agreed = sum(1 for r in scored if abs(r["claude_score"] - r["llm_judge_score"]) <= 2)
            print(f"  Claude vs judge agreement (±2): {agreed}/{len(scored)}")

        # Human feedback vs Claude score
        rated = [r for r in recs if r.get("human_feedback") is not None]
        if rated:
            helpful_ids = {r["recommendation_id"] for r in rated if r["human_feedback"] == 1}
            high_scored = {r["recommendation_id"] for r in rated if (r["claude_score"] or 0) >= 7}
            precision = len(helpful_ids & high_scored) / len(high_scored) if high_scored else 0
            print(f"  Human feedback: {len(helpful_ids)}/{len(rated)} marked helpful")
            print(f"  Precision (score≥7 & human=helpful): {precision:.0%}")
        else:
            print("  No human feedback collected yet.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH
    run(path)
