-- RPC function for vector similarity search with optional filters
create or replace function match_tenders(
    query_embedding vector(384),
    match_count     int      default 20,
    filter_gem      boolean  default false,
    filter_units    text[]   default '{}'
)
returns table (
    id                  uuid,
    nit_number          text,
    notification_number text,
    title               text,
    unit                text,
    opening_date        text,
    detail_url          text,
    is_gem              boolean,
    scraped_at          timestamptz,
    similarity          float
)
language sql stable
as $$
    select
        t.id,
        t.nit_number,
        t.notification_number,
        t.title,
        t.unit,
        t.opening_date,
        t.detail_url,
        t.is_gem,
        t.scraped_at,
        1 - (t.embedding <=> query_embedding) as similarity
    from tenders t
    where
        t.embedding is not null
        and (not filter_gem      or t.is_gem = true)
        and (array_length(filter_units, 1) is null or t.unit = any(filter_units))
    order by t.embedding <=> query_embedding
    limit match_count;
$$;
