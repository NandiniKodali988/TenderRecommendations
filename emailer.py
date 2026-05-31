import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _build_html(recommendations: list[dict], profile_name: str) -> str:
    today = date.today().strftime("%d %B %Y")
    count = len(recommendations)

    score_color = {
        range(9, 11): "#22c55e",  # green
        range(7, 9):  "#f59e0b",  # amber
        range(5, 7):  "#6366f1",  # indigo
    }

    def get_color(score: int) -> str:
        for r, color in score_color.items():
            if score in r:
                return color
        return "#6366f1"

    tender_cards = ""
    for r in recommendations:
        t = r["tender"]
        color = get_color(r["relevance_score"])
        title = t["title"][:120] + "..." if len(t["title"]) > 120 else t["title"]
        gem_badge = '<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">GeM</span>' if t.get("is_gem") else ""

        tender_cards += f"""
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:16px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <span style="background:{color};color:white;padding:3px 10px;border-radius:12px;font-size:13px;font-weight:700;">{r['relevance_score']}/10</span>
            {gem_badge}
            <span style="color:#6b7280;font-size:12px;">{t['unit']}</span>
          </div>
          <div style="font-weight:600;font-size:15px;color:#111827;margin-bottom:6px;">{title}</div>
          <div style="color:#4b5563;font-size:13px;margin-bottom:10px;font-style:italic;">"{r['relevance_reason']}"</div>
          <div style="display:flex;gap:16px;font-size:12px;color:#6b7280;margin-bottom:12px;">
            <span>Ref: {t['notification_number']}</span>
            <span>Opening: {t['opening_date']}</span>
          </div>
          <a href="{t['detail_url']}" style="background:#1d4ed8;color:white;padding:7px 16px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:500;">View Tender</a>
        </div>"""

    return f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;padding:24px;color:#111827;">
      <div style="border-bottom:2px solid #1d4ed8;padding-bottom:16px;margin-bottom:24px;">
        <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:1px;">BHEL Tender Recommendations</div>
        <h1 style="margin:4px 0;font-size:22px;color:#111827;">{today}</h1>
        <div style="color:#4b5563;font-size:14px;">Hi {profile_name} — <strong>{count} relevant tender{'s' if count != 1 else ''}</strong> found for you today.</div>
      </div>
      {tender_cards}
      <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;text-align:center;">
        Tenders sourced from tenders.bhel.com · Recommendations powered by AI
      </div>
    </body></html>"""


def _build_plaintext(recommendations: list[dict], profile_name: str) -> str:
    today = date.today().strftime("%d %B %Y")
    lines = [
        f"BHEL Tender Recommendations — {today}",
        f"Hi {profile_name}, {len(recommendations)} relevant tender(s) found today.",
        "",
    ]
    for r in recommendations:
        t = r["tender"]
        lines += [
            f"[{r['relevance_score']}/10] {t['title']}",
            f"Unit: {t['unit']} | Opening: {t['opening_date']}",
            f"Ref: {t['notification_number']}",
            f"Why: {r['relevance_reason']}",
            f"Link: {t['detail_url']}",
            "",
        ]
    return "\n".join(lines)


def send_digest(recommendations: list[dict], profile: dict) -> None:
    """Send the daily recommendation digest to the sub-contractor."""
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = profile["email"]
    profile_name = profile.get("name", "there")
    today = date.today().strftime("%d %B %Y")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"BHEL Tender Digest — {len(recommendations)} recommendation{'s' if len(recommendations) != 1 else ''} · {today}"
    msg["From"] = f"BHEL Tender Alerts <{gmail_address}>"
    msg["To"] = recipient

    msg.attach(MIMEText(_build_plaintext(recommendations, profile_name), "plain"))
    msg.attach(MIMEText(_build_html(recommendations, profile_name), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, recipient, msg.as_string())

    print(f"  Email sent to {recipient} with {len(recommendations)} recommendations")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    import json
    from pathlib import Path

    results = json.loads(Path("match_results.json").read_text())

    test_profile = {
        "name": results["profile"],
        "email": os.environ["GMAIL_ADDRESS"],  # send test email to yourself
    }

    print(f"Sending test digest to {test_profile['email']}...")
    send_digest(results["recommendations"], test_profile)
    print("Done — check your inbox.")
