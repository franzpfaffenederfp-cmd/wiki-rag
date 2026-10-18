# Wiki-RAG: Obsidian + Postgres/pgvector + OpenAI

Testaufbau für ein durchsuchbares Firmen-Wiki. Obsidian ist der Editor,
Git die Source of Truth, Postgres der Index, OpenAI liefert Embeddings
und Chat-Modell. Jeder andere OpenAI-kompatible Anbieter (z.B. nexos.ai)
lässt sich über die `.env` eintragen.

## Aufbau auf dem VPS

```bash
mkdir -p /docker/wiki-rag && cd /docker/wiki-rag
# Dateien dieses Ordners hierher kopieren, dann:

# 1. Vault klonen (dein privates GitHub-Repo mit den MD-Dateien)
git clone https://github.com/DEINUSER/wiki-vault.git vault

# 2. Konfiguration
cp .env.example .env
sed -i "s/hier-ein-langes-zufallspasswort/$(openssl rand -hex 24)/" .env
nano .env          # EMBED_API_KEY und CHAT_API_KEY eintragen

# 3. Starten
docker compose up -d --build
docker compose ps

# 4. Vault indexieren
docker compose run --rm ingest

# 5. Testen
curl localhost:8080/health
curl -s localhost:8080/ask -H 'Content-Type: application/json' \
  -d '{"question":"Wie läuft der Review-Prozess?"}' | jq
```

## Anbieter für Embeddings und Chat

Embeddings und Chat sind getrennt konfigurierbar und können zu
verschiedenen OpenAI-kompatiblen Anbietern zeigen, nur über die `.env`.
Derzeit beide OpenAI:

```
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_API_KEY=sk-...
EMBED_MODEL=text-embedding-3-small
CHAT_BASE_URL=https://api.openai.com/v1
CHAT_API_KEY=sk-...
CHAT_MODEL=gpt-5.4-nano
```

Leere `*_BASE_URL` / `*_API_KEY` fallen auf `NEXOS_BASE_URL` /
`NEXOS_API_KEY` zurück. Der Ingest nutzt nur die `EMBED_*`-Werte.

- Modellnamen vorher prüfen, welche der Key nutzen darf:
  `curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $KEY" | jq -r '.data[].id'`
- Nach einer Änderung: `docker compose up -d api` (legt den Container neu an
  und liest die `.env` neu ein, `restart` reicht nicht).
- Wer das Embedding-Modell wechselt, muss neu indexieren (`--force`), weil
  alte und neue Vektoren nicht vergleichbar sind.

## Wichtig: Embedding-Dimension

`db/schema.sql` ist auf `vector(1536)` gesetzt. Passt dein Embedding-Modell
nicht dazu (z.B. 1024 oder 3072), **vor dem ersten Start** anpassen:

```bash
sed -i 's/vector(1536)/vector(1024)/g' db/schema.sql
```

Nachträglich ändern heißt: `docker compose down -v` (löscht das Volume),
Schema anpassen, neu starten, neu indexieren.

## Zugriff von außen

Der API-Port ist absichtlich auf `127.0.0.1` gebunden. Für Zugriff von außen
im Cloudflare Zero Trust Dashboard einen Public Hostname am bestehenden
Tunnel anlegen:

- Service Type: `HTTP`
- URL: `localhost:8080`
- Danach mit Cloudflare Access absichern – die API hat selbst keine
  Authentifizierung.

`cloudflared` muss nach dem Neuaufsetzen des Servers neu installiert werden,
der Tunnel selbst existiert im Dashboard aber weiter (gleicher Token).

## Aktualisieren

```bash
cd /docker/wiki-rag/vault && git pull
cd .. && docker compose run --rm ingest
```

Unveränderte Dateien werden über einen Content-Hash übersprungen, gelöschte
Dateien fliegen aus dem Index. Später als GitHub Action bei jedem Merge
automatisieren.

## Was hier bewusst fehlt

- **Authentifizierung** – kommt über Cloudflare Access davor, nicht in die App.
- **Self-hosted Supabase** – für einen Test unnötig schwer. Das Schema ist
  reines Postgres + pgvector und läuft 1:1 auf Supabase, wenn du später
  migrierst.
- **Frontend** – erst die Antwortqualität prüfen, dann UI bauen.

## Der eigentliche Knackpunkt

Nicht die Technik, sondern die Pflege: veraltete Seiten liefern
selbstbewusst falsche Antworten. Nimm `last_review` ins Frontmatter auf und
bau früh einen Report "was ist älter als 6 Monate" – das bringt mehr als
jedes bessere Embedding-Modell.
