-- Enable pgvector extension
create extension if not exists vector;

-- Add embedding column to tenders (384 dims = all-MiniLM-L6-v2 output size)
alter table tenders add column if not exists embedding vector(384);

-- Index for fast cosine similarity search
create index if not exists tenders_embedding_idx
    on tenders using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- Add feedback column to recommendations
alter table recommendations add column if not exists feedback smallint
    check (feedback in (-1, 1));  -- -1 = not relevant, 1 = relevant
