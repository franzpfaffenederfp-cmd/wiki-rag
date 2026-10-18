# Projekt: Wiki-RAG (MDM-Wiki)

Durchsuchbares Wiki für den MDM-Betrieb (BlackBerry UEM, Microsoft Intune) und
österreichische IT-Sicherheits- und Datenschutzvorgaben. Später sollen daraus
Schulungen entstehen. Der Betreiber (Franz) ist IT-Administrator, kein
Entwickler: Befehle kurz erklären, Änderungen einzeln und nachvollziehbar machen.

## Architektur

Obsidian (nur Editor, lokal beim Autor) -> GitHub `wiki-vault` (Wahrheit) ->
Ingest-Script -> nexos.ai (Embeddings) -> Postgres + pgvector -> API /ask ->
nexos.ai (Chat) -> Antwort mit Quellen.

- Code-Repo: https://github.com/franzpfaffenederfp-cmd/wiki-rag (öffentlich).
  Holen per HTTPS, Push per SSH mit eigenem Deploy Key `/root/.ssh/wiki_rag`
  (Schreibrecht nur für `wiki-rag`, eingerichtet über `pushurl` und
  `core.sshCommand` im Repo). Push nur nach Freigabe mit Diff.
- Inhalts-Repo: git@github.com:franzpfaffenederfp-cmd/wiki-vault.git (privat,
  Zugriff per Deploy Key `/root/.ssh/wiki_vault`, nur Lesen)
- Server: Hostinger VPS, Ubuntu 24.04, 8 GB RAM, Pfad `/docker/wiki-rag`
- Der Vault liegt geklont unter `/docker/wiki-rag/vault` und ist NICHT Teil des
  Code-Repos.

## Dateien

- `docker-compose.yml`: Dienste `db` (pgvector/pg16), `api` (FastAPI),
  `ingest` (Profil `tools`, Einmal-Job)
- `db/schema.sql`: Tabellen `documents`, `chunks`, Funktion `search_chunks`
  (Hybrid-Suche: Vektor + Volltext, Reciprocal Rank Fusion, Filter nach
  `scope` und `layer`). Wird nur beim ERSTEN Start der Datenbank ausgeführt.
- `db/002_metadata.sql`: Migration für eine bereits laufende Datenbank.
- `app/ingest.py`: chunkt an Überschriften, schreibt Metadaten-Kopfzeile in
  jeden Chunk, Hash-Vergleich, `--force` indexiert alles neu.
- `app/main.py`: API mit `/health` und `/ask` (Parameter `scope`,
  `exclude_layers`).

## Konfiguration (`.env`, nie committen)

`POSTGRES_PASSWORD`, `NEXOS_API_KEY`, `NEXOS_BASE_URL=https://api.nexos.ai/v1`,
`EMBED_MODEL=Text Embedding 3 Small` (1536 Dimensionen, passt zum Schema),
`CHAT_MODEL=Claude Sonnet 4.6`, `MAX_CHUNK_CHARS`, `MATCH_COUNT`,
`EXCLUDE_LAYERS=betrieb`. Vorlage: `.env.example`.

- Embeddings und Chat sind getrennt konfigurierbar: `EMBED_BASE_URL`,
  `EMBED_API_KEY`, `EMBED_MODEL` und `CHAT_BASE_URL`, `CHAT_API_KEY`,
  `CHAT_MODEL`. Fehlt eine `*_BASE_URL` / `*_API_KEY` oder ist sie leer, gilt
  `NEXOS_BASE_URL` / `NEXOS_API_KEY`. Ein Anbieterwechsel betrifft so nur die
  `.env`. Der Ingest nutzt nur die `EMBED_*`-Werte.
- Ein Embedding-Modell mit anderer Vektorlänge als 1536 braucht zusätzlich
  Schema-Migration und `--force`-Ingest, `.env` allein reicht dann nicht.

- Modell-IDs bei nexos enthalten LEERZEICHEN und werden im Klartext verwendet.
  In der `.env` ohne Anführungszeichen, in JSON-Bodies in Anführungszeichen.
- Der nexos-Key und die `.env` sind nirgends gesichert. Nie in Chat, Logs,
  Commits oder Ausgaben wiedergeben.

## Wiki-Konventionen (Inhalt)

Jede Aussage steht an genau EINER Stelle. Ebenen per Frontmatter-Feld `layer`:
`richtlinien` (werkzeugneutral), `plattform` (Android/Apple), `umsetzung`
(pro System), `extern` (gespiegelte Behördenquellen, read-only), `betrieb`
(Recherchen und Arbeitsdokumente, in Standardabfragen ausgeblendet).

Weitere Felder: `scope: [uem]` / `[intune]` (fehlt = gilt für alle),
`source`, `verbindlich: true/false`, `hinweis`, `owner`, `last_review`,
`audience`. Das Modell sieht diese Angaben über eine Kopfzeile in jedem Chunk.

## Bekannte Stolpersteine

- Docker Compose: Argumente für den Ingest NACH dem Befehl angeben:
  `docker compose run --rm ingest python ingest.py --force`
  (`... ingest --force` scheitert).
- Frontmatter-Datumswerte (`last_review: 2026-08-24`) sind in YAML Datumsobjekte
  und müssen vor dem JSON-Speichern in Text gewandelt werden (ist in
  `parse_frontmatter` gelöst, nicht entfernen).
- Änderungen am Code immer auch in GitHub sichern. Lokale Patches gingen schon
  einmal bei `git stash` / `git pull` verloren.
- Heredocs (`<<'EOF'`): `EOF` muss ganz links stehen.
- `search_chunks` hat eine neue Signatur. Ändert sich die Funktion, muss die
  Migration auf die laufende Datenbank angewendet werden, `schema.sql` allein
  reicht dort nicht.

## Sicherheitsregeln

- Ports nur an `127.0.0.1` binden. Nichts direkt ins Internet öffnen.
- Die API hat keine eigene Anmeldung. Externer Zugriff nur über Cloudflare
  Tunnel MIT Cloudflare Access davor.
- Der Vault-Key `wiki_vault` bleibt schreibgeschützt. Schreibrecht hat nur
  `wiki_rag`, und nur für das Code-Repo.
- Keine destruktiven Befehle (`docker compose down -v`, `rm -rf`, `git reset
  --hard`, `git push --force`) ohne ausdrückliche Rückfrage.

## Fremde Dienste auf demselben Server (NICHT anfassen)

Auf dem Server laufen bereits andere Docker-Dienste, die nicht zu diesem
Projekt gehören (Stand 17.10.2026):

- laufend: `openclaw`, `openclaw-sandbox` (Compose-Projekt unter
  `/opt/stack/openclaw`), `rv001-linkbot`
- gestoppt: `hermes`, `hermes-sandbox`, `n8n`, `n8n-postgres`, `traefik`
- Volumes: `hermes_sandbox_*`, `n8n_*`, `openclaw_sandbox_*`
- Netzwerke: `proxy`, `n8n_internal`, `hermes_sandbox`, `openclaw_sandbox`

Regeln:

- Nur Ressourcen anfassen, deren Name mit `wiki-rag` beginnt (Container
  `wiki-rag-*`, Volume `wiki-rag_pgdata`, Netzwerk `wiki-rag_default`).
- Gestoppte Container und ihre Volumes bleiben erhalten. `docker system prune`,
  `docker container prune`, `docker volume prune`, `docker network prune` und
  `docker image prune -a` sind VERBOTEN, weil sie genau diese gestoppten
  Container und deren unbenutzte Volumes (n8n-Daten, n8n-Postgres) löschen.
- Fremde Container nie stoppen, starten, neu starten oder löschen.
- `docker compose` nur im Ordner `/docker/wiki-rag` ausführen. `/opt/stack`
  und alles darunter nicht ändern.
- Dem Netzwerk `proxy` nicht beitreten, Wiki-RAG bleibt isoliert.
- Von außen lauscht derzeit nur SSH (Port 22). Unsere Dienste nutzen
  `127.0.0.1:8080` (API) und `127.0.0.1:5433` (Datenbank), beide waren frei.
  Vor jedem neuen Port mit `ss -tlnp` prüfen.
- Arbeitsspeicher: rund 5 GB frei. Wiki-RAG sparsam halten, keine großen
  zusätzlichen Dienste starten.

## Aktueller Stand

Docker, git und jq sind installiert, `/docker` ist leer, `.env` und Deploy Key
fehlen noch. Zu tun, in dieser Reihenfolge:

1. Prüfen, was auf dem Server schon vorhanden ist (Docker, git, jq, Repos, `.env`).
2. Deploy Key neu erzeugen; Franz trägt ihn auf GitHub ein.
3. `wiki-rag` und `wiki-vault` klonen, `.env` anlegen (Key von Franz abfragen,
   nicht raten).
4. `docker compose up -d --build`, dann Ingest, dann `/health` prüfen.
5. Tests: Betriebsvereinbarung (Fund aus `betrieb`, nur mit
   `"exclude_layers":[]`), Scope-Filter (`"scope":"intune"`), Frage ohne
   Treffer muss "steht nicht im Wiki" liefern.

## Offene Vorhaben

- Cloudflare Tunnel + Access (Subdomain `wiki`)
- RIS-Fetcher (OGD-API v2.6) für DSG, TKG 2021, NISG 2026, ArbVG §§ 96/96a
  nach `extern/`, mit `source_url` und `fetched_at` im Frontmatter
- CERT.at-RSS-Feeds
- GitHub Action oder Cron für automatisches Indexieren
- Einfaches Chat-Frontend
- Report: Seiten mit `last_review` älter als 6 Monate
- Echte Inhalte (20-30 Seiten) statt Testseiten

Hinweis zu Quellen: Das Österreichische Informationssicherheitshandbuch sperrt
automatisierte Zugriffe per robots.txt und wird nur manuell eingebunden. Bei
Handbüchern und Leitfäden ist die Lizenz meist nicht offen, dort Zusammenfassung
plus Link statt Volltext.
