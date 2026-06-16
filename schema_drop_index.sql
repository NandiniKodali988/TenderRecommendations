-- Drop ivfflat index — causes missed results on filtered queries with small datasets.
-- Sequential scan is correct and fast for < 1000 rows.
-- Re-add an HNSW index once the dataset grows beyond ~1000 tenders.
drop index if exists tenders_embedding_idx;
