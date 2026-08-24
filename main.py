"""Query-API: Frage -> gefilterte Hybrid-Suche in Postgres -> Antwort mit Quellen."""

import os
from typing import List, Optional

import psycopg
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
CHAT_MODEL = os.environ["CHAT_MODEL"]
MATCH_COUNT = int(os.environ.get("MATCH_COUNT", "8"))

# Ebenen, die in normalen Abfragen nicht auftauchen sollen. "betrieb" enthält
# Arbeitsdokumente und Recherchen, keine gültigen Vorgaben.
DEFAULT_EXCLUDED_LAYERS = [
    x.strip() for x in os.environ.get("EXCLUDE_LAYERS", "betrieb").split(",") if x.strip()
]

client = OpenAI(
    base_url=os.environ.get("NEXOS_BASE_URL", "https://api.nexos.ai/v1"),
    api_key=os.environ["NEXOS_API_KEY"],
)

SYSTEM_PROMPT = """Du beantwortest Fragen ausschließlich auf Basis der
bereitgestellten Wiki-Auszüge.

Jeder Auszug beginnt mit einer Kopfzeile in eckigen Klammern. Werte sie aus:

- "verbindlich: NEIN" oder "Herkunft: recherche": Die Aussage ist eine
  Arbeitsgrundlage, keine gültige Vorgabe. Sage das ausdrücklich dazu und
  verweise auf die Originalquelle.
- "gilt für: uem" bzw. "gilt für: intune": Nenne bei jedem Umsetzungsschritt
  ausdrücklich, für welches System er gilt. Übertrage niemals einen Schritt
  von einem System auf das andere.
- "gilt für: alle Systeme": Die Aussage ist systemunabhängig.

Weitere Regeln:
- Steht die Antwort nicht in den Auszügen, sage das klar. Rate nicht.
- Verweise im Text auf die Quelle in der Form [Dateipfad].
- Widersprechen sich zwei Auszüge, benenne den Widerspruch, statt ihn zu glätten.
- Gib niemals eine Formulierung als wörtliches Zitat einer Behörde aus, wenn
  im Auszug nicht eindeutig steht, dass es sich um den Originalwortlaut handelt.
- Antworte knapp und sachlich auf Deutsch."""

app = FastAPI(title="Wiki RAG")


class Ask(BaseModel):
    question: str
    # "uem" oder "intune" - begrenzt die Suche auf dieses System plus alle
    # systemunabhängigen Seiten.
    scope: Optional[str] = None
    # Ebenen ausblenden; None benutzt die Vorgabe, [] zeigt alles.
    exclude_layers: Optional[List[str]] = None


@app.get("/health")
def health():
    with psycopg.connect(DATABASE_URL) as conn:
        docs = conn.execute("select count(*) from documents").fetchone()[0]
        chunks = conn.execute("select count(*) from chunks").fetchone()[0]
        layers = conn.execute(
            """select coalesce(frontmatter->>'layer', '(ohne)') as layer, count(*)
               from documents group by 1 order by 1"""
        ).fetchall()
    return {
        "status": "ok",
        "documents": docs,
        "chunks": chunks,
        "layers": {row[0]: row[1] for row in layers},
        "excluded_by_default": DEFAULT_EXCLUDED_LAYERS,
    }


@app.post("/ask")
def ask(payload: Ask):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Frage ist leer.")

    excluded = (
        DEFAULT_EXCLUDED_LAYERS if payload.exclude_layers is None else payload.exclude_layers
    )
    embedding = client.embeddings.create(model=EMBED_MODEL, input=[question]).data[0].embedding

    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "select * from search_chunks(%s::vector, %s, %s, %s, %s)",
            (str(embedding), question, MATCH_COUNT, payload.scope, excluded or None),
        ).fetchall()

    if not rows:
        return {"answer": "Dazu steht nichts im Wiki.", "sources": [], "scope": payload.scope}

    context = "\n\n---\n\n".join(f"[{row[1]}]\n{row[4]}" for row in rows)
    completion = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Wiki-Auszüge:\n\n{context}\n\nFrage: {question}"},
        ],
    )

    sources, seen = [], set()
    for row in rows:
        if row[1] in seen:
            continue
        seen.add(row[1])
        sources.append(
            {
                "path": row[1],
                "title": row[2],
                "heading": row[3],
                "layer": row[5],
                "scope": row[6] or "alle Systeme",
                "verbindlich": row[7],
                "quelle": row[8],
                "score": row[9],
            }
        )

    return {
        "answer": completion.choices[0].message.content,
        "sources": sources,
        "scope": payload.scope,
        "excluded_layers": excluded,
    }
