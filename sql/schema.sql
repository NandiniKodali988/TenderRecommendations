-- Tenders: raw scraped records from tenders.bhel.com
create table if not exists tenders (
    id                  uuid primary key default gen_random_uuid(),
    nit_number          text unique not null,
    notification_number text,
    title               text,
    unit                text,
    opening_date        text,
    detail_url          text,
    is_gem              boolean default false,
    scraped_at          timestamptz default now()
);

-- Profiles: sub-contractor preferences
create table if not exists profiles (
    id                      uuid primary key default gen_random_uuid(),
    name                    text not null,
    email                   text unique not null,
    work_scope              text,                        -- free text: what the company does
    preferred_units         text[] default '{}',         -- e.g. {"BHEL, Hyderabad","BHEL, Trichy"}
    gem_only                boolean default true,        -- only GeM tenders?
    preferred_tender_types  text[] default '{}',         -- e.g. {"Work Contract","Service Contract"}
    min_value               numeric,
    max_value               numeric,
    include_keywords        text[] default '{}',
    exclude_keywords        text[] default '{}',
    created_at              timestamptz default now(),
    updated_at              timestamptz default now()
);

-- Recommendations: match results per profile per tender
create table if not exists recommendations (
    id                uuid primary key default gen_random_uuid(),
    tender_id         uuid references tenders(id) on delete cascade,
    profile_id        uuid references profiles(id) on delete cascade,
    relevance_score   integer check (relevance_score between 1 and 10),
    relevance_reason  text,
    emailed_at        timestamptz,
    created_at        timestamptz default now(),
    unique (tender_id, profile_id)   -- no duplicate matches
);

-- Auto-update updated_at on profile changes
create or replace function update_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger profiles_updated_at
    before update on profiles
    for each row execute function update_updated_at();
