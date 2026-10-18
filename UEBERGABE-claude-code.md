# Übergabe an Claude Code (Stand 18.10.2026, abends)

Lies zuerst `CLAUDE.md` im Projektordner. Diese Datei ergänzt es um den aktuellen
Stand. Franz ist IT-Administrator, kein Entwickler: Änderungen einzeln und kurz
erklärt, vor jedem Commit den Diff zeigen, Push nur nach Freigabe.

## 1. Aktueller Stand

- **Läuft:** `wiki-rag-db-1` und `wiki-rag-api-1` (gestartet mit
  `docker compose up -d`), `/health` ok.
- **Anbieter:** Embeddings und Chat laufen über **OpenAI direkt**, nicht mehr
  über nexos. Eigener Key für Wiki-RAG (nicht der von Hermes/OpenClaw).
  - `EMBED_MODEL=text-embedding-3-small` (1536 Dimensionen, passt zum Schema)
  - `CHAT_MODEL=gpt-5.4-nano` (`gpt-5.6-nano` gibt es für den Key nicht)
  - `EMBED_BASE_URL` / `CHAT_BASE_URL` = `https://api.openai.com/v1`
  - Die `NEXOS_*`-Zeilen stehen noch in der `.env`, werden aber nicht benutzt,
    solange die `EMBED_*`/`CHAT_*`-Werte gesetzt sind.
- **Index:** 1 Dokument (`betrieb/quellenregister-behoerden.md`, 20 Chunks).
  `README.md` im Vault wird als leer übersprungen. Weil der gesamte Inhalt in
  der Ebene `betrieb` liegt, antworten Standardabfragen derzeit immer
  "Dazu steht nichts im Wiki."
- **Git:** Push per eigenem Deploy Key `/root/.ssh/wiki_rag` (Schreibrecht nur
  `wiki-rag`). Der Vault-Key `wiki_vault` bleibt schreibgeschützt.

## 2. Erledigt am 18.10.2026

- Konfiguration getrennt: `EMBED_BASE_URL`, `EMBED_API_KEY`, `EMBED_MODEL`,
  `CHAT_BASE_URL`, `CHAT_API_KEY`, `CHAT_MODEL`. Leere oder fehlende Werte
  fallen auf `NEXOS_BASE_URL` / `NEXOS_API_KEY` zurück. Vorlage: `.env.example`.
- Deploy Key mit Schreibrecht für `wiki-rag` eingerichtet und getestet.
- Umstieg auf OpenAI, erster erfolgreicher Ingest.
- Tests aus CLAUDE.md Schritt 5:
  - Betriebsvereinbarung mit `"exclude_layers":[]`: richtige Antwort
    (§ 96 Abs. 1 Z 3, § 96a ArbVG), als nicht verbindlich gekennzeichnet.
  - `"scope":"intune"`: Seite wird gefunden. Der Filter ist aber **nicht
    wirklich geprüft**, weil eine Seite nur für `uem` fehlt.
  - Ohne Treffer: "Dazu steht nichts im Wiki." Themenfremde Frage mit allen
    Ebenen: Modell sagt korrekt, dass es nicht im Wiki steht.
- `/ask` liefert auch bei "nichts im Wiki" das Feld `excluded_layers`.

## 3. Bekannte Schwächen (nicht behoben)

- Bei Antworten "steht nicht im Wiki" listet `/ask` trotzdem die gefundenen
  Auszüge unter `sources`. Ein Frontend würde damit irreführende Quellen zeigen.
  Am besten zusammen mit dem Frontend lösen.
- `sources` zeigt pro Datei nur den ersten passenden Abschnitt.

## 4. Nächste Schritte

1. Echte Inhalte im Vault: mindestens eine Seite in `richtlinien` oder
   `umsetzung`, dazu eine Seite nur mit `scope: [uem]`, damit der Scope-Test
   sinnvoll ist. `Home.md` anlegen.
2. Danach: `cd vault && git pull`, dann
   `docker compose run --rm ingest python ingest.py`, Scope-Test wiederholen.
3. Offene Vorhaben aus `CLAUDE.md` (Cloudflare Tunnel + Access, RIS-Fetcher,
   automatisches Indexieren, Frontend, Review-Report).

Nach Änderungen an der `.env`: `docker compose up -d` (legt `api` neu an und
liest die `.env` neu). `docker compose start` / `restart` reichen dafür nicht.
Wer das Embedding-Modell wechselt, muss mit `--force` neu indexieren.

## 5. Offen bei Franz

- OpenAI: Datenschutz prüfen (Region, AVV, Nutzung der Daten zum Training),
  bevor echte Inhalte indexiert werden. Budget-Limit für den Wiki-RAG-Key bzw.
  das Projekt setzen.
- nexos: Support-Ticket zu den versehentlich gekauften Workspace-Credits
  (Quittung #2133-6811), Antwort frühestens 19.10.2026. Key `Hostinger-Stack`
  hat kein Limit. Ob nexos überhaupt noch gebraucht wird, ist offen.
- `/root/.ssh/authorized_keys` wurde am 18.10.2026 um 12:12 geändert, nicht
  durch Claude. Prüfen, ob das gewollt war.

## 6. Regeln (aus CLAUDE.md, hier zur Sicherheit wiederholt)

- Nur Ressourcen mit Namen `wiki-rag*` anfassen. Fremde Container
  (`openclaw`, `openclaw-sandbox`, `rv001-linkbot`, `hermes*`, `n8n*`, `traefik`),
  ihre Volumes und Netzwerke nie stoppen, starten, ändern oder löschen.
- Verboten: `docker system prune`, `docker container/volume/network prune`,
  `docker image prune -a`, `docker compose down -v`, `rm -rf`, `git reset --hard`,
  `git push --force`.
- API-Keys und die `.env` nie ausgeben, loggen oder committen. Kopien wie
  `.env.save` sind per `.gitignore` ausgeschlossen.
- Ports nur an `127.0.0.1`. Kein Beitritt zum Netzwerk `proxy`.
