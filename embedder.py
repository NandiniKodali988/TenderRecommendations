from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def tender_text(tender: dict) -> str:
    """Combine the most descriptive fields into a single string to embed."""
    parts = [
        tender.get("title") or "",
        tender.get("unit") or "",
        tender.get("notification_number") or "",
    ]
    return " | ".join(p for p in parts if p)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.tolist()


def embed_tenders(tenders: list[dict]) -> list[tuple[str, list[float]]]:
    """Return (tender_id, embedding) pairs for a list of tenders."""
    texts = [tender_text(t) for t in tenders]
    vectors = embed_texts(texts)
    return [(t["id"], v) for t, v in zip(tenders, vectors)]


def embed_query(text: str) -> list[float]:
    """Embed a profile work scope string for similarity search."""
    return embed_texts([text])[0]


def _to_pgvector(vector: list[float]) -> str:
    """Format a float list as a pgvector string e.g. '[0.1,0.2,...]'"""
    return "[" + ",".join(str(x) for x in vector) + "]"


def store_embeddings(client, id_vector_pairs: list[tuple[str, list[float]]]) -> int:
    """Write embeddings back to the tenders table in Supabase."""
    if not id_vector_pairs:
        return 0
    for tender_id, vector in id_vector_pairs:
        client.table("tenders").update(
            {"embedding": _to_pgvector(vector)}
        ).eq("id", tender_id).execute()
    return len(id_vector_pairs)


def find_similar_tenders(
    client,
    query_embedding: list[float],
    top_k: int = 20,
    only_gem: bool = False,
    preferred_units: list[str] = None,
) -> list[dict]:
    """
    Vector similarity search via Supabase RPC.
    Returns the top_k most similar tenders to the query embedding.
    """
    result = client.rpc(
        "match_tenders",
        {
            "query_embedding": _to_pgvector(query_embedding),
            "match_count": top_k,
            "filter_gem": only_gem,
            "filter_units": preferred_units or [],
        },
    ).execute()
    return result.data


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from database import get_client

    client = get_client()

    print("Loading model...")
    get_model()
    print(f"Model loaded: {MODEL_NAME}\n")

    tenders = client.table("tenders").select("*").execute().data
    unembedded = [t for t in tenders if not t.get("embedding")]
    print(f"Tenders without embeddings: {len(unembedded)}")

    if unembedded:
        print("Embedding and storing...")
        pairs = embed_tenders(unembedded)
        count = store_embeddings(client, pairs)
        print(f"Stored embeddings for {count} tenders")
    else:
        print("All tenders already embedded.")

    # Quick similarity test
    print("\nTest: searching for 'civil construction erection power plant'")
    query_vec = embed_query("civil construction erection power plant")

    # Direct cosine similarity without RPC (for testing before RPC is set up)
    all_embedded = client.table("tenders").select("id, title, unit, embedding").execute().data
    embedded_only = [t for t in all_embedded if t.get("embedding")]

    if embedded_only:
        import numpy as np
        import json
        q = np.array(query_vec)
        scored = []
        for t in embedded_only:
            raw = t["embedding"]
            v = np.array(json.loads(raw) if isinstance(raw, str) else raw)
            sim = float(np.dot(q, v))
            scored.append((sim, t))
        scored.sort(reverse=True)
        print("\nTop 5 most similar tenders:")
        for sim, t in scored[:5]:
            print(f"  {sim:.3f} — {t['title'][:70]} | {t['unit']}")
