"""Query-API: Frage -> Hybrid-Suche in Postgres -> Antwort mit Quellen."""

import os

import psycopg
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
CHAT_MODEL = os.environ["CHAT_MODEL"]
MATCH_COUNT = int(os.environ.get("MATCH_COUNT", "8"))

client = OpenAI(
    base_url=os.environ.get("NEXOS_BASE_URL", "https://api.nexos.ai/v1"),
    api_key=os.environ["NEXOS_API_KEY"],
)

SYSTEM_PROMPT = """Du beantwortest Fragen ausschließlich auf Basis der
bereitgestellten Wiki-Auszüge. Regeln:
- Steht die Antwort nicht in den Auszügen, sage das klar. Rate nicht.
- Verweise im Text auf die Quelle in der Form [Dateipfad].
- Antworte knapp und sachlich auf Deutsch."""

app = FastAPI(title="Wiki RAG")


class Ask(BaseModel):
    question: str


@app.get("/health")
def health():
    with psycopg.connect(DATABASE_URL) as conn:
        docs = conn.execute("select count(*) from documents").fetchone()[0]
        chunks = conn.execute("select count(*) from chunks").fetchone()[0]
    return {"status": "ok", "documents": docs, "chunks": chunks}


@app.post("/ask")
def ask(payload: Ask):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Frage ist leer.")

    embedding = client.embeddings.create(model=EMBED_MODEL, input=[question]).data[0].embedding

    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "select * from search_chunks(%s::vector, %s, %s)",
            (str(embedding), question, MATCH_COUNT),
        ).fetchall()

    if not rows:
        return {"answer": "Dazu steht nichts im Wiki.", "sources": []}

    context = "\n\n---\n\n".join(
        f"[{row[1]}]\n{row[4]}" for row in rows
    )
    completion = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Wiki-Auszüge:\n\n{context}\n\nFrage: {question}"},
        ],
    )

    sources = []
    for row in rows:
        entry = {"path": row[1], "title": row[2], "heading": row[3], "score": row[5]}
        if entry["path"] not in [s["path"] for s in sources]:
            sources.append(entry)

    return {"answer": completion.choices[0].message.content, "sources": sources}
