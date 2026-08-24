-- Migration 002: Metadaten-Filter für die Hybrid-Suche
-- Anwenden auf eine bereits laufende Datenbank:
--   docker compose exec -T db psql -U wiki -d wiki < db/002_metadata.sql
--
-- Die Frontmatter-Felder liegen bereits in documents.frontmatter (jsonb).
-- Es braucht daher keine neue Spalte, nur eine erweiterte Suchfunktion.

drop function if exists search_chunks(vector, text, int, int);
drop function if exists search_chunks(vector, text, int, text, text[], int);

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
