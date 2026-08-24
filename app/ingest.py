"""Liest den Obsidian-Vault, chunkt die Markdown-Dateien und schreibt
Embeddings nach Postgres. Unveränderte Dateien werden übersprungen."""

import hashlib
import os
import re
from pathlib import Path

import psycopg
import yaml
from openai import OpenAI
from psycopg.types.json import Jsonb

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/vault"))
DATABASE_URL = os.environ["DATABASE_URL"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
MAX_CHARS = int(os.environ.get("MAX_CHUNK_CHARS", "2000"))
BATCH_SIZE = 32

client = OpenAI(
    base_url=os.environ.get("NEXOS_BASE_URL", "https://api.nexos.ai/v1"),
    api_key=os.environ["NEXOS_API_KEY"],
)

HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")


def parse_frontmatter(text: str):
    """Trennt YAML-Frontmatter vom Inhalt."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, parts[2].lstrip("\n")


def split_sections(body: str):
    """Zerlegt den Text an Überschriften (H1-H3) in (heading, text)-Paare."""
    sections, heading, buf = [], None, []
    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            if buf and "".join(buf).strip():
                sections.append((heading, "\n".join(buf).strip()))
            heading, buf = match.group(2).strip(), []
        else:
            buf.append(line)
    if buf and "".join(buf).strip():
        sections.append((heading, "\n".join(buf).strip()))
    return sections


def split_long(text: str):
    """Teilt zu lange Abschnitte an Absatzgrenzen."""
    if len(text) <= MAX_CHARS:
        return [text]
    out, current = [], ""
    for para in text.split("\n\n"):
        if current and len(current) + len(para) + 2 > MAX_CHARS:
            out.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current.strip():
        out.append(current.strip())
    return out


def build_chunks(title: str, body: str):
    """Erzeugt die finalen Chunks. Titel und Überschrift werden in den Text
    aufgenommen, damit ein Chunk auch isoliert verständlich bleibt."""
    chunks = []
    for heading, text in split_sections(body):
        for piece in split_long(text):
            prefix = f"{title} > {heading}" if heading else title
            chunks.append((heading, f"# {prefix}\n\n{piece}"))
    return chunks


def embed(texts):
    vectors = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        response = client.embeddings.create(model=EMBED_MODEL, input=batch)
        vectors.extend(item.embedding for item in response.data)
    return vectors


def main():
    files = sorted(p for p in VAULT_PATH.rglob("*.md") if ".obsidian" not in p.parts)
    print(f"{len(files)} Markdown-Dateien gefunden in {VAULT_PATH}")

    seen_paths = []
    with psycopg.connect(DATABASE_URL) as conn:
        for path in files:
            rel = str(path.relative_to(VAULT_PATH))
            seen_paths.append(rel)
            raw = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

            row = conn.execute(
                "select content_hash from documents where path = %s", (rel,)
            ).fetchone()
            if row and row[0] == digest:
                print(f"  unverändert: {rel}")
                continue

            meta, body = parse_frontmatter(raw)
            title = meta.get("title") or path.stem
            chunks = build_chunks(title, body)
            if not chunks:
                print(f"  leer, übersprungen: {rel}")
                continue

            vectors = embed([c[1] for c in chunks])

            doc_id = conn.execute(
                """
                insert into documents (path, title, frontmatter, content_hash, updated_at)
                values (%s, %s, %s, %s, now())
                on conflict (path) do update
                    set title = excluded.title,
                        frontmatter = excluded.frontmatter,
                        content_hash = excluded.content_hash,
                        updated_at = now()
                returning id
                """,
                (rel, title, Jsonb(meta), digest),
            ).fetchone()[0]

            conn.execute("delete from chunks where document_id = %s", (doc_id,))
            with conn.cursor() as cur:
                cur.executemany(
                    """insert into chunks (document_id, chunk_index, heading, content, embedding)
                       values (%s, %s, %s, %s, %s::vector)""",
                    [
                        (doc_id, i, heading, content, str(vector))
                        for i, ((heading, content), vector) in enumerate(zip(chunks, vectors))
                    ],
                )
            conn.commit()
            print(f"  indexiert: {rel} ({len(chunks)} Chunks)")

        # Gelöschte Dateien auch aus dem Index entfernen
        if seen_paths:
            deleted = conn.execute(
                "delete from documents where path <> all(%s) returning path", (seen_paths,)
            ).fetchall()
            for (gone,) in deleted:
                print(f"  entfernt: {gone}")
            conn.commit()

    print("Fertig.")


if __name__ == "__main__":
    main()
