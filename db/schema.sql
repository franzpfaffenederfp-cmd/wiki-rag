-- Schema für Obsidian-Wiki-RAG
-- Wird beim ersten Start des DB-Containers automatisch ausgeführt.
-- ACHTUNG: vector(1536) muss zur Dimension deines Embedding-Modells passen.

create extension if not exists vector;

create table if not exists documents (
    id           bigserial primary key,
    path         text unique not null,
    title        text,
    frontmatter  jsonb not null default '{}'::jsonb,
    content_hash text not null,
    updated_at   timestamptz not null default now()
);

create table if not exists chunks (
    id          bigserial primary key,
    document_id bigint not null references documents(id) on delete cascade,
    chunk_index int not null,
    heading     text,
    content     text not null,
    embedding   vector(1536),
    fts         tsvector generated always as (to_tsvector('german', content)) stored
);

create index if not exists chunks_document_id_idx on chunks (document_id);
create index if not exists chunks_fts_idx on chunks using gin (fts);
create index if not exists chunks_embedding_idx
    on chunks using hnsw (embedding vector_cosine_ops);

-- Hybrid-Suche: Vektor-Treffer und Volltext-Treffer werden per
-- Reciprocal Rank Fusion zusammengeführt. Rein semantische Suche
-- findet Fachbegriffe und Abkürzungen oft schlecht, deshalb beides.
create or replace function search_chunks(
    query_embedding vector(1536),
    query_text      text,
    match_count     int default 8,
    rrf_k           int default 50
)
returns table (
    chunk_id      bigint,
    document_path text,
    title         text,
    heading       text,
    content       text,
    score         double precision
)
language sql stable as $$
    with semantic as (
        select c.id, row_number() over (order by c.embedding <=> query_embedding) as rank
        from chunks c
        where c.embedding is not null
        order by c.embedding <=> query_embedding
        limit match_count * 4
    ),
    keyword as (
        select c.id,
               row_number() over (
                   order by ts_rank_cd(c.fts, websearch_to_tsquery('german', query_text)) desc
               ) as rank
        from chunks c
        where c.fts @@ websearch_to_tsquery('german', query_text)
        limit match_count * 4
    )
    select c.id,
           d.path,
           d.title,
           c.heading,
           c.content,
           (coalesce(1.0 / (rrf_k + s.rank), 0.0)
          + coalesce(1.0 / (rrf_k + k.rank), 0.0))::double precision as score
    from chunks c
    join documents d on d.id = c.document_id
    left join semantic s on s.id = c.id
    left join keyword  k on k.id = c.id
    where s.id is not null or k.id is not null
    order by score desc
    limit match_count;
$$;
