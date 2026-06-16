-- Drop the broken ivfflat index (lists=100 requires at least 100 rows, we have ~57)
drop index if exists tenders_embedding_idx;

-- Recreate with lists=10 (rule of thumb: sqrt of row count)
-- For small datasets pgvector falls back to sequential scan anyway which is fine
create index tenders_embedding_idx
    on tenders using ivfflat (embedding vector_cosine_ops)
    with (lists = 10);
