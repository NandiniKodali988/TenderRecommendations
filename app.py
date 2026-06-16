import os
import secrets
import hashlib
import base64
import urllib.parse
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

import httpx
from supabase import create_client, Client
from database import get_client as get_service_client, save_feedback, save_recommendation
from matcher import match_profile

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
APP_URL = os.environ.get("APP_URL", "http://localhost:8501").strip()

BHEL_UNITS = [
    "BHEL, Hyderabad", "BHEL, Haridwar", "BHEL, Bhopal", "BHEL, Trichy",
    "BHEL, Chennai", "BHEL, Ranipet", "BHEL, Jhansi", "BHEL, Varanasi",
    "BHEL, Jagdishpur", "BHEL, Rudrapur", "BHEL, RAIPUR",
    "BHEL EDN, Bangalore", "BHEL, New Delhi",
    "BHEL, Power Sector", "BHEL, PSSR", "BHEL, PSNR", "BHEL, PSWR",
    "BHEL, Industry Sector", "Corp Office Noida", "Corp office Delhi",
    "HEAVY PLATES and VESSELS PLANT", "International Operations Division",
]

TENDER_TYPES = [
    "Work Contract", "Service Contract", "Supply", "Buy",
    "Turnkey", "Open Tender", "Rate Contract", "Empanelment",
]

st.set_page_config(page_title="BHEL Tender Recommendations", page_icon="📋", layout="wide")


# --- PKCE helpers ---

@st.cache_resource
def _pkce_store() -> dict:
    # Server-side store — persists across browser redirects within the same process.
    # Single-user safe: for multi-user production, key by session ID instead.
    return {"verifier": ""}


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _google_auth_url() -> str:
    verifier, challenge = _pkce_pair()
    _pkce_store()["verifier"] = verifier  # Save before redirect
    qs = urllib.parse.urlencode({
        "provider": "google",
        "redirect_to": APP_URL,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{SUPABASE_URL}/auth/v1/authorize?{qs}"


# --- Auth helpers ---

def get_anon_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_authed_client() -> Client:
    client = get_anon_client()
    if "access_token" in st.session_state:
        try:
            client.auth.set_session(
                st.session_state["access_token"],
                st.session_state["refresh_token"],
            )
        except Exception:
            for key in ["user", "access_token", "refresh_token"]:
                st.session_state.pop(key, None)
            st.rerun()
    return client


# --- Handle OAuth callback ---
params = st.query_params
if "code" in params:
    verifier = _pkce_store().get("verifier", "")
    try:
        _client = get_anon_client()
        response = _client.auth.exchange_code_for_session({
            "auth_code": params["code"],
            "code_verifier": verifier,
        })
        st.session_state["access_token"] = response.session.access_token
        st.session_state["refresh_token"] = response.session.refresh_token
        st.session_state["user"] = response.user
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Login failed: {e}")
        st.stop()


# --- Require login ---
if "user" not in st.session_state:
    st.title("BHEL Tender Recommendations")
    st.markdown("Sign in to view your personalised tender recommendations.")
    st.link_button("Sign in with Google", _google_auth_url(), type="primary")
    st.stop()


# --- Logged-in state ---
client = get_authed_client()
user = st.session_state["user"]


# --- Data helpers ---

def _fresh_client() -> Client:
    """Always return a new authenticated client to avoid stale HTTP/2 connections."""
    return get_authed_client()


def load_profile():
    try:
        result = (
            _fresh_client().table("profiles")
            .select("*")
            .eq("user_id", user.id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except httpx.RemoteProtocolError:
        st.rerun()


def save_profile(data: dict):
    data["user_id"] = user.id
    existing = load_profile()
    c = _fresh_client()
    if existing:
        c.table("profiles").update(data).eq("id", existing["id"]).execute()
    else:
        c.table("profiles").insert(data).execute()


def load_recommendations(profile_id: str):
    result = (
        _fresh_client().table("recommendations")
        .select("*, tenders(*)")
        .eq("profile_id", profile_id)
        .order("relevance_score", desc=True)
        .execute()
    )
    return result.data


# --- Sidebar ---
st.sidebar.title("📋 BHEL Tenders")
st.sidebar.caption(f"Signed in as {user.email}")
if st.sidebar.button("Sign out"):
    for key in ["user", "access_token", "refresh_token"]:
        st.session_state.pop(key, None)
    st.rerun()

page = st.sidebar.radio("Navigate", ["My Recommendations", "My Profile"])
st.sidebar.divider()
st.sidebar.caption("Tenders sourced from tenders.bhel.com\nRecommendations powered by AI")


# --- Recommendations Page ---
if page == "My Recommendations":
    st.title("My Tender Recommendations")

    profile = load_profile()
    if not profile:
        st.warning("No profile set up yet. Go to **My Profile** to get started.")
        st.stop()

    recs = load_recommendations(profile["id"])

    btn_label = "Generate recommendations now" if not recs else "Refresh recommendations"
    btn_type = "primary" if not recs else "secondary"
    if st.button(btn_label, type=btn_type):
        with st.spinner("Running matcher — this takes about 30 seconds..."):
            try:
                service_client = get_service_client()
                # Clear stale recommendations so all tenders are re-scored against the current profile
                service_client.table("recommendations").delete().eq("profile_id", profile["id"]).execute()
                results = match_profile(service_client, profile)
                for r in results:
                    save_recommendation(
                        service_client,
                        tender_id=r["tender_id"],
                        profile_id=profile["id"],
                        score=r["score"],
                        reason=r["reason"],
                    )
                st.success(f"Done — {len(results)} recommendations generated.")
                st.rerun()
            except Exception as e:
                st.error(f"Pipeline failed: {e}")

    if not recs:
        st.info("No recommendations yet. The daily digest also runs every morning at 8 AM IST.")
        st.stop()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Recommendations", len(recs))
    col2.metric("High Relevance (8+)", sum(1 for r in recs if r["relevance_score"] >= 8))
    col3.metric("GeM Tenders", sum(1 for r in recs if r["tenders"]["is_gem"]))

    st.divider()

    with st.expander("Filters", expanded=False):
        min_score = st.slider("Minimum relevance score", 1, 10, 5)
        gem_filter = st.checkbox("GeM tenders only", value=False)

    filtered = [
        r for r in recs
        if r["relevance_score"] >= min_score
        and (not gem_filter or r["tenders"]["is_gem"])
    ]

    st.caption(f"Showing {len(filtered)} of {len(recs)} recommendations")

    for r in filtered:
        t = r["tenders"]
        score = r["relevance_score"]

        color = "🟢" if score >= 8 else "🟡" if score >= 6 else "🔵"
        gem_tag = " · `GeM`" if t["is_gem"] else ""
        title = t["title"][:100] + "..." if len(t["title"]) > 100 else t["title"]

        with st.expander(f"{color} **{score}/10** — {title}{gem_tag}"):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(f"**Why recommended:** {r['relevance_reason']}")
                st.markdown(f"**Unit:** {t['unit']}")
                st.markdown(f"**Ref:** {t['notification_number']}")
            with col2:
                st.markdown(f"**Opening:** {t['opening_date']}")
                if r.get("emailed_at"):
                    st.caption(f"Emailed on {r['emailed_at'][:10]}")
                st.link_button("View Tender →", t["detail_url"])

            st.divider()
            feedback_val = r.get("feedback")
            fb_col1, fb_col2, fb_col3 = st.columns([1, 1, 6])
            with fb_col1:
                thumbs_up_type = "primary" if feedback_val == 1 else "secondary"
                if st.button("👍 Helpful", key=f"up_{r['id']}", type=thumbs_up_type):
                    save_feedback(client, r["id"], 1)
                    st.rerun()
            with fb_col2:
                thumbs_down_type = "primary" if feedback_val == -1 else "secondary"
                if st.button("👎 Not helpful", key=f"down_{r['id']}", type=thumbs_down_type):
                    save_feedback(client, r["id"], -1)
                    st.rerun()
            with fb_col3:
                if feedback_val == 1:
                    st.caption("Feedback saved — future recommendations will lean toward tenders like this.")
                elif feedback_val == -1:
                    st.caption("Feedback saved — this type of tender will be deprioritised.")


# --- Profile Page ---
elif page == "My Profile":
    st.title("My Profile")
    st.caption("Your preferences control which tenders get recommended to you each morning.")

    profile = load_profile()

    with st.form("profile_form"):
        st.subheader("Contact")
        name = st.text_input("Your name / company name", value=profile["name"] if profile else "")
        email = st.text_input("Email address for daily digest", value=profile["email"] if profile else "")

        st.subheader("Work Scope")
        work_scope = st.text_area(
            "Describe what your company does",
            value=profile["work_scope"] if profile else "",
            height=120,
            placeholder="e.g. Civil construction, structural fabrication, erection and commissioning of industrial equipment, boiler and turbine installation for power plants.",
        )

        st.subheader("Filters")
        preferred_units = st.multiselect(
            "Preferred BHEL locations",
            options=BHEL_UNITS,
            default=profile["preferred_units"] if profile else ["BHEL, Hyderabad"],
        )
        gem_only = st.toggle(
            "GeM tenders only",
            value=profile["gem_only"] if profile else True,
        )
        preferred_tender_types = st.multiselect(
            "Preferred tender types (leave blank for all)",
            options=TENDER_TYPES,
            default=profile["preferred_tender_types"] if profile else [],
        )

        st.subheader("Keywords (optional)")
        include_raw = st.text_input(
            "Include keywords (comma-separated)",
            value=", ".join(profile["include_keywords"]) if profile else "",
            placeholder="e.g. civil, erection, fabrication",
        )
        exclude_raw = st.text_input(
            "Exclude keywords (comma-separated)",
            value=", ".join(profile["exclude_keywords"]) if profile else "",
            placeholder="e.g. printing, stationery",
        )

        submitted = st.form_submit_button("Save Profile", type="primary")

    if submitted:
        if not name or not email or not work_scope:
            st.error("Name, email, and work scope are required.")
        else:
            include_kw = [k.strip() for k in include_raw.split(",") if k.strip()]
            exclude_kw = [k.strip() for k in exclude_raw.split(",") if k.strip()]
            save_profile({
                "name": name,
                "email": email,
                "work_scope": work_scope,
                "preferred_units": preferred_units,
                "gem_only": gem_only,
                "preferred_tender_types": preferred_tender_types,
                "include_keywords": include_kw,
                "exclude_keywords": exclude_kw,
            })
            st.success("Profile saved! Your preferences will apply from the next morning's digest.")
            st.rerun()
