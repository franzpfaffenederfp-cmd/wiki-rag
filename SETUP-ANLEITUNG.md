# Schritt-für-Schritt: Wiki-RAG auf dem Hostinger-VPS

Server: `srv1416376` / `147.93.63.96` · GitHub: `franzpfaffenederfp-cm`

Arbeite die Teile A–H der Reihe nach ab. Nach jedem Teil steht, woran du
erkennst, dass es geklappt hat.

---

## Teil A — GitHub-Repo für den Vault anlegen

**A1.** Öffne https://github.com/new

**A2.** Ausfüllen:
- Repository name: `wiki-vault`
- Visibility: **Private**
- Haken bei "Add a README file"
- → **Create repository**

**A3.** Lege 3–5 Testseiten an. Klick im Repo auf **Add file → Create new
file**, Dateiname `handbuch/review-prozess.md`, Inhalt z.B.:

```markdown
---
title: Review-Prozess für Wiki-Seiten
owner: franz
last_review: 2026-08-24
tags: [prozess, wiki]
---

# Review-Prozess

Jede Änderung an einer Wiki-Seite läuft über einen Pull Request.
Der im Frontmatter eingetragene Owner prüft fachlich, ein zweiter
Kollege liest gegen.

## Fristen

Seiten müssen alle 6 Monate überprüft werden. Das Feld `last_review`
wird dabei aktualisiert.
```

Wichtig: Nimm **echte Inhalte**, bei denen du beurteilen kannst, ob die
Antworten später stimmen. Mit Blindtext kannst du nichts testen.

✅ **Geschafft, wenn:** Das Repo enthält mehrere `.md`-Dateien mit
Frontmatter.

---

## Teil B — Deploy Key, damit der Server das Repo lesen darf

Ein privates Repo kann der Server nicht einfach klonen. Ein Deploy Key ist
ein Lese-Schlüssel nur für dieses eine Repo.

**B1.** Auf dem Server einen Schlüssel erzeugen:

```bash
ssh-keygen -t ed25519 -C "wiki-vault-deploy" -f /root/.ssh/wiki_vault -N ""
cat /root/.ssh/wiki_vault.pub
```

**B2.** Die ausgegebene Zeile (beginnt mit `ssh-ed25519 ...`) kopieren.

**B3.** Im Browser: https://github.com/franzpfaffenederfp-cm/wiki-vault/settings/keys
→ **Add deploy key**
- Title: `hostinger-vps`
- Key: die kopierte Zeile einfügen
- "Allow write access" **NICHT** anhaken
- → **Add key**

**B4.** SSH so konfigurieren, dass der Schlüssel verwendet wird:

```bash
cat >> /root/.ssh/config <<'EOF'
Host github.com
    IdentityFile /root/.ssh/wiki_vault
    IdentitiesOnly yes
EOF
chmod 600 /root/.ssh/config
```

**B5.** Testen:

```bash
ssh -T git@github.com
```

✅ **Geschafft, wenn:** Die Antwort lautet sinngemäß "Hi
franzpfaffenederfp-cm/wiki-vault! You've successfully authenticated, but
GitHub does not provide shell access."

---

## Teil C — Server vorbereiten

**C1.** Updates und Git installieren:

```bash
apt update && apt upgrade -y
apt install -y git curl jq
```

**C2.** Projektverzeichnis anlegen:

```bash
mkdir -p /docker/wiki-rag
cd /docker/wiki-rag
```

**C3.** Die Projektdateien (`docker-compose.yml`, `.env.example`, Ordner
`app/` und `db/`) vom Rechner hochladen. Auf **deinem PC** im Ordner, in dem
der entpackte `wiki-rag`-Ordner liegt:

```bash
scp -r wiki-rag/* root@147.93.63.96:/docker/wiki-rag/
```

Unter Windows geht das genauso in PowerShell.

**C4.** Auf dem Server prüfen:

```bash
cd /docker/wiki-rag && ls -R
```

✅ **Geschafft, wenn:** Du siehst `docker-compose.yml`, `.env.example`,
`app/` (mit `main.py`, `ingest.py`, `Dockerfile`, `requirements.txt`) und
`db/schema.sql`.

---

## Teil D — Vault klonen

```bash
cd /docker/wiki-rag
git clone git@github.com:franzpfaffenederfp-cm/wiki-vault.git vault
ls vault
```

✅ **Geschafft, wenn:** Deine Markdown-Dateien unter
`/docker/wiki-rag/vault/` liegen.

---

## Teil E — nexos.ai konfigurieren

**E1.** Im nexos-Dashboard: **Gateway → API keys → Generate API Key**.
Schlüssel kopieren (beginnt mit `nexos-`).

**E2.** Auf dem Server als Variable setzen (nur für diese Sitzung, zum
Testen):

```bash
export NEXOS_API_KEY="nexos-DEIN-KEY"
```

**E3.** Verfügbare Modelle auflisten:

```bash
curl -s https://api.nexos.ai/v1/models \
  -H "Authorization: Bearer $NEXOS_API_KEY" | jq -r '.data[].id'
```

Notiere dir zwei IDs: eine für **Embeddings** (Name enthält meist
`embedding`) und eine zum **Chatten** (z.B. ein Claude- oder GPT-Modell).

**E4.** Konfigurationsdatei anlegen:

```bash
cd /docker/wiki-rag
cp .env.example .env
sed -i "s/hier-ein-langes-zufallspasswort/$(openssl rand -hex 24)/" .env
nano .env
```

Trage ein: `NEXOS_API_KEY`, `EMBED_MODEL`, `CHAT_MODEL` (die IDs aus E3).
Speichern mit `Strg+O`, `Enter`, `Strg+X`.

✅ **Geschafft, wenn:** `cat .env` zeigt Key, beide Modell-IDs und ein
langes Passwort.

---

## Teil F — Embedding-Dimension prüfen (nicht überspringen!)

Die Datenbank wird auf eine feste Vektorgröße festgelegt. Passt sie nicht
zum Modell, musst du später alles löschen und neu aufbauen.

**F1.** Dimension abfragen:

```bash
cd /docker/wiki-rag
source .env
curl -s https://api.nexos.ai/v1/embeddings \
  -H "Authorization: Bearer $NEXOS_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$EMBED_MODEL\",\"input\":\"test\"}" \
  | jq '.data[0].embedding | length'
```

**F2.** Kommt eine andere Zahl als `1536` heraus, Schema anpassen — Beispiel
für 1024:

```bash
sed -i 's/vector(1536)/vector(1024)/g' db/schema.sql
grep -n "vector(" db/schema.sql
```

✅ **Geschafft, wenn:** Die Zahl aus F1 mit der Zahl in `db/schema.sql`
übereinstimmt.

---

## Teil G — Starten und indexieren

**G1.** Container bauen und starten:

```bash
cd /docker/wiki-rag
docker compose up -d --build
docker compose ps
```

**G2.** Warten, bis `db` als `healthy` angezeigt wird (ca. 15 Sekunden),
dann den Vault indexieren:

```bash
docker compose run --rm ingest
```

Du siehst pro Datei eine Zeile mit der Anzahl der Chunks.

**G3.** Test:

```bash
curl -s localhost:8080/health | jq
curl -s localhost:8080/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Wie läuft der Review-Prozess?"}' | jq
```

✅ **Geschafft, wenn:** `/health` zeigt eine Dokument- und Chunk-Anzahl > 0,
und `/ask` liefert eine Antwort samt `sources` mit deinen Dateipfaden.

**Wenn etwas schiefgeht:**

```bash
docker compose logs api --tail 50
docker compose logs db --tail 50
```

---

## Teil H — Zugriff über Cloudflare

**H1.** `cloudflared` installieren (nach dem Neuaufsetzen ist es weg, dein
Tunnel im Dashboard existiert aber weiter):

```bash
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  -o /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared noble main" \
  > /etc/apt/sources.list.d/cloudflared.list
apt update && apt install -y cloudflared
```

**H2.** Im Cloudflare Zero Trust Dashboard → **Networks → Tunnels** deinen
Tunnel öffnen, den Token kopieren und auf dem Server:

```bash
cloudflared service install DEIN_TUNNEL_TOKEN
systemctl status cloudflared
```

**H3.** Im Tunnel unter **Public Hostname → Add a public hostname**:
- Subdomain: `wiki`
- Domain: deine Domain
- Service Type: `HTTP`
- URL: `localhost:8080`

**H4.** ⚠️ **Zugriffsschutz.** Die API hat keine eigene Anmeldung. Lege in
Zero Trust unter **Access → Applications** eine Self-hosted Application für
`wiki.deinedomain` an und erlaube nur eure E-Mail-Domain. Ohne diesen
Schritt kann jeder im Internet euer Wiki abfragen.

✅ **Geschafft, wenn:** Der Aufruf von `https://wiki.deinedomain/health` erst
nach Login funktioniert.

---

## Laufender Betrieb

**Inhalte aktualisieren:** In Obsidian bearbeiten → in GitHub mergen → dann
auf dem Server:

```bash
cd /docker/wiki-rag/vault && git pull
cd .. && docker compose run --rm ingest
```

Unveränderte Dateien werden übersprungen, gelöschte fliegen aus dem Index.

**Obsidian anbinden:** Repo lokal klonen, den Ordner in Obsidian als Vault
öffnen, Community-Plugin "Git" installieren für automatischen Sync.

**Komplett neu aufsetzen** (löscht alle Daten):

```bash
cd /docker/wiki-rag
docker compose down -v
docker compose up -d --build
docker compose run --rm ingest
```

---

## Reihenfolge der nächsten Ausbaustufen

1. Antwortqualität mit echten Fragen prüfen — erst danach lohnt weiterer Aufwand
2. Ingest per GitHub Action bei jedem Merge automatisieren
3. Einfaches Chat-Frontend statt curl
4. Report "Seiten mit `last_review` älter als 6 Monate"
