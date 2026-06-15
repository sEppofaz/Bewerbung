# Bewerbungsseite – Josef Fischer

## URLs & Deployment

- **Live:** `https://fischer-josef.de/`
- **Admin:** `https://fischer-josef.de/admin/`
- **Lokal:** `~/Dropbox/Apps/Claude/Bewerbung/`
- **GitHub:** `sEppofaz/Bewerbung` (privat)
- **Server:** `/opt/bewerbung/` auf Hetzner (89.167.104.145)
- **Port:** `5004`
- **Service:** `bewerbung` (systemd)

## Deployment-Flow

```bash
# Lokal committen + pushen
cd ~/Library/CloudStorage/Dropbox/Apps/Claude/Bewerbung
git add -p && git commit -m "..." && git push

# Auf Server deployen
ssh root@89.167.104.145 "git -C /opt/bewerbung pull && systemctl restart bewerbung"
```

## Dateistruktur

```
main.py              ← FastAPI Backend (alle Routen)
requirements.txt     ← weasyprint, jinja2, cairosvg, ...
templates/
  cv_print.html      ← Jinja2-Template für CV-PDF (WeasyPrint)
static/
  index.html         ← Landing (Split: Login | VKO)
  app/
    index.html       ← Firmen-Bereich (Auth-geschützt, CV dynamisch)
  admin/
    index.html       ← Admin-PWA (6 Tabs: +Lebenslauf)
    login.html       ← Admin-Login
  manifest.json
  sw.js              ← Cache: bewerbung-v1
assets/
  lebenslauf.pdf     ← Original EN-PDF (Fallback, in .gitignore!)
  lebenslauf_de.pdf  ← Generiert via Admin (in .gitignore!)
  lebenslauf_en.pdf  ← Generiert via Admin (in .gitignore!)
icons/               ← Auto-generiert via cairosvg (in .gitignore!)
bewerbung.db         ← SQLite (in .gitignore!)
```

## Umgebungsvariablen (in /etc/pka/secrets.env)

| Variable                | Beschreibung                        |
|-------------------------|-------------------------------------|
| `BEWERBUNG_ADMIN_TOKEN` | Admin-Login-Token (neu anlegen)     |
| `BEWERBUNG_SECRET_KEY`  | Session-Signing-Key (neu anlegen)   |
| `TELEGRAM_BOT_TOKEN`    | Schon vorhanden                     |
| `TELEGRAM_CHAT_ID`      | Schon vorhanden                     |
| `HTTPS_ONLY`            | `true` auf Server, `false` lokal    |
| `CLAUDE_API_KEY`        | Für Auto-Übersetzung DE→EN (Haiku)  |

## Server-Setup (einmalig)

```bash
# 1. Git-Repo klonen
cd /opt && git clone https://github.com/sEppofaz/Bewerbung.git bewerbung

# 2. venv + Dependencies
cd /opt/bewerbung
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. Ordner anlegen
mkdir -p assets icons

# 4. Berechtigungen
chown -R webhook:webhook /opt/bewerbung
chmod 755 /opt/bewerbung/assets /opt/bewerbung/icons

# 5. Systemd-Service (siehe systemd/bewerbung.service)
cp systemd/bewerbung.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable bewerbung && systemctl start bewerbung
```

## Systemd-Service

Datei: `/etc/systemd/system/bewerbung.service`

```ini
[Unit]
Description=Bewerbung Josef Fischer
After=network.target

[Service]
User=webhook
WorkingDirectory=/opt/bewerbung
EnvironmentFile=/etc/pka/secrets.env
Environment=HTTPS_ONLY=true
ExecStart=/opt/bewerbung/venv/bin/uvicorn main:app --host 127.0.0.1 --port 5004
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

## nginx-Config (neuer server-Block für fischer-josef.de)

```nginx
server {
    listen 80;
    server_name fischer-josef.de www.fischer-josef.de;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name fischer-josef.de www.fischer-josef.de;

    ssl_certificate     /etc/letsencrypt/live/fischer-josef.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/fischer-josef.de/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;

    location / {
        proxy_pass http://127.0.0.1:5004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        add_header Cache-Control "no-store";
    }
}
```

## Icon

- **Motiv:** Briefcase (Lucide), Navy `#1e3a5f`, weißes Icon
- **Methode:** B (cairosvg, server-seitig, auto-generiert)
- **Cache-Name SW:** `bewerbung-v1` → hochzählen bei Icon/Manifest-Änderungen

## Inhalte eintragen (TODO Josef)

- [ ] `static/app/index.html`: Über-mich-Text, Wunschstelle, Skills ergänzen
- [ ] `static/app/index.html`: Lebenslauf-Einträge (Berufserfahrung, Ausbildung)
- [ ] `static/index.html`: VKO-Logo unter `/assets/vko-logo.png` ablegen, `<img>` Tag einkommentieren
- [ ] `assets/lebenslauf.pdf` auf Server kopieren: `scp lebenslauf.pdf root@89.167.104.145:/opt/bewerbung/assets/`
- [ ] Secrets in `/etc/pka/secrets.env` eintragen: `BEWERBUNG_ADMIN_TOKEN`, `BEWERBUNG_SECRET_KEY`

## Pitfalls

- `assets/lebenslauf.pdf` ist in `.gitignore` → manuell per scp auf Server kopieren
- `icons/` und `bewerbung.db` sind in `.gitignore` → werden auf Server auto-erstellt
- `HTTPS_ONLY=true` im systemd → lokal testen mit `HTTPS_ONLY=false` in shell
- Icon-Berechtigungen: `chown webhook:webhook /opt/bewerbung/icons` nach erstem Deployment
- SSL-Zertifikat via certbot (Let's Encrypt), Ablauf 2026-09-13, Auto-Renewal aktiv
- Python 3.12: Deutsche Anführungszeichen „" im Python-Code verboten → SyntaxError! Immer ' oder " (ASCII) verwenden
- CV-Daten in SQLite `content`-Tabelle (Key `main`, JSON). Lebenslauf wird dynamisch geladen, nicht hardcoded
- PDF-Workflow: Admin → Lebenslauf bearbeiten (DE) → „Übersetzen + PDFs generieren" → Claude Haiku übersetzt → WeasyPrint baut PDFs
- `lebenslauf_de.pdf`, `lebenslauf_en.pdf`, `lebenslauf.pdf` alle in `.gitignore` → manuell auf Server

## Token-Format

`JF-XXXX-YYYY` (Großbuchstaben + Ziffern, zufällig generiert)
Beispiel: `JF-K8M2-P9VX`
