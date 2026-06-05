import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from database import get_client, save_feedback

app = FastAPI(title="BHEL Tender Recommendations API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic models ---

class ProfileIn(BaseModel):
    name: str
    email: str
    work_scope: str
    preferred_units: list[str] = []
    gem_only: bool = True
    preferred_tender_types: list[str] = []
    include_keywords: list[str] = []
    exclude_keywords: list[str] = []


class ProfileOut(ProfileIn):
    id: str
    created_at: str | None = None
    updated_at: str | None = None


class TenderOut(BaseModel):
    id: str
    nit_number: str
    notification_number: str
    title: str
    unit: str
    opening_date: str
    detail_url: str
    is_gem: bool
    scraped_at: str | None = None


class RecommendationOut(BaseModel):
    id: str
    tender_id: str
    profile_id: str
    relevance_score: int
    relevance_reason: str
    feedback: int | None = None
    emailed_at: str | None = None
    tender: TenderOut | None = None


class FeedbackIn(BaseModel):
    value: int

    @field_validator("value")
    @classmethod
    def value_must_be_valid(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("value must be 1 (helpful) or -1 (not helpful)")
        return v


# --- Routes ---

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/profiles", response_model=list[ProfileOut])
def list_profiles():
    client = get_client()
    result = client.table("profiles").select("*").execute()
    return result.data


@app.post("/profiles", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(data: ProfileIn):
    client = get_client()
    result = client.table("profiles").insert(data.model_dump()).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create profile")
    return result.data[0]


@app.get("/profiles/{profile_id}", response_model=ProfileOut)
def get_profile(profile_id: str):
    client = get_client()
    result = client.table("profiles").select("*").eq("id", profile_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result.data[0]


@app.put("/profiles/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: str, data: ProfileIn):
    client = get_client()
    result = (
        client.table("profiles")
        .update(data.model_dump())
        .eq("id", profile_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result.data[0]


@app.get("/profiles/{profile_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations(
    profile_id: str,
    min_score: int = 1,
    gem_only: bool = False,
):
    client = get_client()
    query = (
        client.table("recommendations")
        .select("*, tenders(*)")
        .eq("profile_id", profile_id)
        .gte("relevance_score", min_score)
        .order("relevance_score", desc=True)
    )
    result = query.execute()

    recs = result.data
    if gem_only:
        recs = [r for r in recs if r.get("tenders", {}).get("is_gem")]

    return [
        {**r, "tender": r.pop("tenders", None)}
        for r in recs
    ]


@app.post("/recommendations/{rec_id}/feedback", status_code=status.HTTP_200_OK)
def submit_feedback(rec_id: str, data: FeedbackIn):
    client = get_client()
    result = client.table("recommendations").select("id").eq("id", rec_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    save_feedback(client, rec_id, data.value)
    return {"rec_id": rec_id, "feedback": data.value}
