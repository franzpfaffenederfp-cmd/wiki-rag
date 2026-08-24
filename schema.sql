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

-- Hybrid-Suche mit Metadaten-Filter: Vektor- und Volltext-Treffer werden
-- per Reciprocal Rank Fusion zusammengeführt. Rein semantische Suche findet
-- Fachbegriffe und Abkürzungen oft schlecht, deshalb beides.
create function search_chunks(
    query_embedding vector(1536),
    query_text      text,
    match_count     int     default 8,
    filter_scope    text    default null,
    exclude_layers  text[]  default null,
    rrf_k           int     default 50
)
returns table (
    chunk_id      bigint,
    document_path text,
    title         text,
    heading       text,
    content       text,
    layer         text,
    scope         text,
    verbindlich   boolean,
    quelle        text,
    score         double precision
)
language sql stable as $$
    -- Erst filtern, dann ranken. Andersherum würde das Limit die
    -- passenden Treffer abschneiden, bevor der Filter greift.
    with allowed as (
        select c.id, c.embedding, c.fts
        from chunks c
        join documents d on d.id = c.document_id
        where (
                filter_scope is null
                or d.frontmatter->'scope' is null
                -- Seiten ohne scope gelten für alle Systeme (z.B. Richtlinien)
                or d.frontmatter->'scope' @> to_jsonb(filter_scope)
              )
          and (
                exclude_layers is null
                or coalesce(d.frontmatter->>'layer', '') <> all(exclude_layers)
              )
    ),
    semantic as (
        select a.id, row_number() over (order by a.embedding <=> query_embedding) as rank
        from allowed a
        where a.embedding is not null
        order by a.embedding <=> query_embedding
        limit match_count * 4
    ),
    keyword as (
        select a.id,
               row_number() over (
                   order by ts_rank_cd(a.fts, websearch_to_tsquery('german', query_text)) desc
               ) as rank
        from allowed a
        where a.fts @@ websearch_to_tsquery('german', query_text)
        limit match_count * 4
    )
    select c.id,
           d.path,
           d.title,
           c.heading,
           c.content,
           d.frontmatter->>'layer',
           case
               when jsonb_typeof(d.frontmatter->'scope') = 'array'
                   then (select string_agg(x, ', ')
                         from jsonb_array_elements_text(d.frontmatter->'scope') x)
               else d.frontmatter->>'scope'
           end,
           case
               when d.frontmatter->>'verbindlich' in ('true', 'false')
                   then (d.frontmatter->>'verbindlich')::boolean
               else null
           end,
           d.frontmatter->>'source',
           (coalesce(1.0 / (rrf_k + s.rank), 0.0)
          + coalesce(1.0 / (rrf_k + k.rank), 0.0))::double precision
    from chunks c
    join documents d on d.id = c.document_id
    left join semantic s on s.id = c.id
    left join keyword  k on k.id = c.id
    where s.id is not null or k.id is not null
    order by 10 desc
    limit match_count;
$$;

-- Beschleunigt das Filtern nach Frontmatter-Feldern
create index if not exists documents_frontmatter_idx
    on documents using gin (frontmatter);
