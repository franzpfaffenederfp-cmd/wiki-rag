# Übergabe an Claude Code (Stand 18.10.2026)

Lies zuerst `CLAUDE.md` im Projektordner. Diese Datei ergänzt es um den aktuellen
Stand und einen konkreten Auftrag. Franz ist IT-Administrator, kein Entwickler:
Änderungen einzeln und kurz erklärt, vor jedem Commit den Diff zeigen.

## 1. Aktueller Stand

- Die Wiki-RAG-Container (`wiki-rag-db-1`, `wiki-rag-api-1`) sind von Franz
  **absichtlich gestoppt** (`docker compose stop`). Daten im Volume
  `wiki-rag_pgdata` sind erhalten. **Nicht starten**, bis Franz es sagt.
- Die Datenbank ist leer (0 Dokumente). Der Ingest ist noch nie erfolgreich
  gelaufen.
- Blocker: Die nexos-API antwortet auf Embeddings mit **HTTP 402**
  ("You're out of AI credits"). Der Key ist gültig (`GET /v1/models` liefert 200).
  - API-Credits stehen auf 51/51 (leer).
  - Der Checkout für API-Credits zeigt "Purchases are temporarily unavailable".
  - Franz hat versehentlich 10.000 **Workspace**-Credits gekauft (120 €, Quittung
    #2133-6811). Die zählen nicht für die API. Support-Ticket ist offen, Antwort
    frühestens Montag 19.10.2026.
  - Fast alle bisherigen API-Kosten stammen vom nexos-Key `Hostinger-Stack`
    (ca. 39,77 $ von 41,39 $), nicht vom Key `WIKI-RAG-2`. Vermutlich verbrauchen
    andere Dienste auf dem Server die Credits. Das ist nur eine Vermutung, nicht
    geprüft.
- Lokal im Repo existiert ein ungepushter Commit `2b8b950` (`.gitignore`). Die
  Push-Methode ist noch nicht entschieden (Empfehlung: eigener Deploy Key mit
  Schreibrecht nur für `wiki-rag`, der Vault-Key bleibt schreibgeschützt; Push nur
  nach Freigabe mit Diff).

## 2. Warum nexos, und was sonst möglich wäre

nexos wurde gewählt, weil Franz dort schon ein Konto hatte. Es ist keine
technische Notwendigkeit. Die API ist OpenAI-kompatibel.

| Variante | Embeddings | Chat | Aufwand |
|---|---|---|---|
| nexos (jetzt) | Text Embedding 3 Small (1536) | Claude Sonnet 4.6 | keiner |
| OpenAI direkt | text-embedding-3-small (1536, Schema bleibt) | GPT-Modell | nur `.env` |
| Anthropic direkt | gibt es dort nicht | Claude per API-Key (nicht im Max-Abo enthalten, Abrechnung pro Token) | Code-Zweig für Anthropic-SDK |
| Lokal | z. B. multilingual-E5 auf dem Server | weiter extern nötig | Schema und Vektorlänge ändern, `--force` Ingest |

Preise und Datenschutzdetails (Region, AVV) sind nicht recherchiert. Franz muss
sie pro Anbieter prüfen.

Entscheidung: Erst die Antwort vom nexos-Support abwarten. Parallel die
Konfiguration so trennen, dass ein späterer Wechsel nur `.env` betrifft.

## 3. Auftrag: Konfiguration für Embeddings und Chat trennen

Ziel: Embeddings und Chat können unabhängig voneinander zu verschiedenen Anbietern
zeigen, ohne weitere Code-Änderung.

Neue Variablen in `.env` und `.env.example`:

```
EMBED_BASE_URL=
EMBED_API_KEY=
EMBED_MODEL=
CHAT_BASE_URL=
CHAT_API_KEY=
CHAT_MODEL=
```

Anforderungen:

1. **Abwärtskompatibel.** Fehlen die neuen Variablen, fallen sie auf
   `NEXOS_BASE_URL` und `NEXOS_API_KEY` zurück. Die bestehende `.env` muss ohne
   Änderung weiter funktionieren.
2. `app/main.py`: zwei OpenAI-Clients, einer für Embeddings, einer für Chat.
3. `app/ingest.py`: der Embedding-Client liest die `EMBED_*`-Variablen.
4. `docker-compose.yml` braucht voraussichtlich keine Änderung (`env_file: .env`),
   bitte prüfen.
5. Das Schema (`vector(1536)`) bleibt unverändert. Ein Anbieter mit anderer
   Vektorlänge wäre ein eigener Schritt mit Migration und `--force`-Ingest.
6. `CLAUDE.md` (Abschnitt Konfiguration) und `README.md` aktualisieren.
7. Nach der Änderung nur **bauen und die Syntax prüfen** (`docker compose build`,
   `python -m py_compile`). Keine Container starten, keine API-Aufrufe, solange
   die Credits fehlen.
8. Diff zeigen, auf Freigabe warten, dann committen. Push nur nach Freigabe.

## 4. Danach, sobald die API wieder Credits hat

Franz bestätigt: `curl`-Test auf Embeddings liefert 200. Dann:

1. `docker compose start`, `/health` prüfen.
2. Ingest: `docker compose run --rm ingest python ingest.py --force`
3. Tests aus Schritt 5 in `CLAUDE.md`:
   - "Brauche ich für MDM eine Betriebsvereinbarung?" nur mit
     `"exclude_layers":[]`, weil die Seite in der Ebene `betrieb` liegt.
   - `"scope":"intune"`. Dafür fehlt noch eine Seite nur für `uem`, damit der
     Filter sinnvoll prüfbar ist.
   - Eine Frage ohne Treffer muss "steht nicht im Wiki" liefern.

## 5. Offen bei Franz (nicht Teil des Auftrags)

- nexos-Support (Montag): Erstattung oder Umwandlung der Workspace-Credits,
  Checkout reparieren.
- Limits für die nexos-Keys setzen: `Hostinger-Stack` (derzeit unbegrenzt),
  `WIKI-RAG-2` (derzeit 50 $, gewünscht ca. 5 $). Erst danach API-Credits
  aufladen, am besten mit 10 Credits zum Testen.
- Echte Wiki-Seiten schreiben und `Home.md` in den Vault legen.

## 6. Regeln (aus CLAUDE.md, hier zur Sicherheit wiederholt)

- Nur Ressourcen mit Namen `wiki-rag*` anfassen. Fremde Container
  (`openclaw`, `openclaw-sandbox`, `rv001-linkbot`, `hermes*`, `n8n*`, `traefik`),
  ihre Volumes und Netzwerke nie stoppen, starten, ändern oder löschen.
- Verboten: `docker system prune`, `docker container/volume/network prune`,
  `docker image prune -a`, `docker compose down -v`, `rm -rf`, `git reset --hard`,
  `git push --force`.
- Den nexos-Key und die `.env` nie ausgeben, loggen oder committen.
- Ports nur an `127.0.0.1`. Kein Beitritt zum Netzwerk `proxy`.
