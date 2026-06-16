"""
Bewerbungsseite Josef Fischer – Backend
FastAPI + SQLite + Telegram | Port 5004
"""
import os, sqlite3, secrets, string, json as json_lib
from datetime import datetime
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
import requests as http

BASE          = Path(__file__).parent
DB_PATH       = BASE / "bewerbung.db"
ICONS_DIR     = BASE / "icons"
STATIC_DIR    = BASE / "static"
ASSETS_DIR    = BASE / "assets"
TEMPLATES_DIR = BASE / "templates"

_jinja = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)

ADMIN_TOKEN = os.environ.get("BEWERBUNG_ADMIN_TOKEN", "")
TG_BOT      = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = os.environ.get("TELEGRAM_CHAT_ID", "")
SECRET_KEY  = os.environ.get("BEWERBUNG_SECRET_KEY", secrets.token_hex(32))
HTTPS_ONLY  = os.environ.get("HTTPS_ONLY", "true").lower() == "true"
CLAUDE_KEY  = os.environ.get("CLAUDE_API_KEY", "")

app = FastAPI(docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=86400 * 30,
    https_only=HTTPS_ONLY,
    session_cookie="bw_session",
)

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS tokens (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                token_str   TEXT UNIQUE NOT NULL,
                firma_name  TEXT NOT NULL,
                erstellt_am TEXT NOT NULL,
                aktiv       INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id   INTEGER,
                event_type TEXT NOT NULL,
                page       TEXT,
                ts         TEXT NOT NULL,
                ip         TEXT,
                FOREIGN KEY(token_id) REFERENCES tokens(id)
            );
            CREATE TABLE IF NOT EXISTS content (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kontakt_anfragen (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT,
                email     TEXT NOT NULL,
                nachricht TEXT NOT NULL,
                ts        TEXT NOT NULL,
                token_id  INTEGER
            );
        """)

init_db()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_DEFAULT_CONTENT = {
    "ueber_mich": {
        "de": "Dipl.-Wirtschaftsingenieur mit über 20 Jahren Erfahrung im Engineering-Dienstleistungsbereich und Projektmanagement. Zuletzt als Prokurist und Centre Manager bei QuEST Global in München verantwortlich für bis zu 320 Mitarbeiter und 28 Mio. $ Umsatz. Neben meiner Führungsrolle entwickle ich eigenständig Webanwendungen und Automatisierungslösungen – mit KI-Unterstützung durch Claude Code (Vibe-Coding). Ich kombiniere strategisches Denken mit technischer Umsetzungsstärke und einem ausgeprägten Sinn für effiziente Prozesse.",
        "en": "Graduate engineer (Dipl.-Wirtschaftsingenieur) with 20+ years in engineering services and project management. Most recently Prokurist (proxy) and Centre Manager at QuEST Global Munich, responsible for up to 320 employees and USD 28M revenue. Alongside my leadership role I independently develop web applications and automation solutions using AI-assisted development (Vibe-Coding with Claude Code). I combine strategic thinking with strong hands-on execution and a keen sense for efficient processes."
    },
    "skills": [
        {"de": "AI-assisted Development", "en": "AI-assisted Development", "highlight": True},
        {"de": "Programmmanagement", "en": "Programme Management", "highlight": True},
        {"de": "Business Development", "en": "Business Development", "highlight": True},
        {"de": "Change Management", "en": "Change Management", "highlight": False},
        {"de": "Prozessberatung", "en": "Process Consulting", "highlight": False},
        {"de": "Engineering Services", "en": "Engineering Services", "highlight": False},
        {"de": "Führung (bis 320 MA)", "en": "Leadership (up to 320 staff)", "highlight": False},
        {"de": "Progressive Web Apps", "en": "Progressive Web Apps", "highlight": False},
        {"de": "FastAPI · Python", "en": "FastAPI · Python", "highlight": False},
        {"de": "HTML · CSS · JavaScript", "en": "HTML · CSS · JavaScript", "highlight": False},
        {"de": "Linux · nginx · Server", "en": "Linux · nginx · Server", "highlight": False},
        {"de": "Prozessautomatisierung", "en": "Process Automation", "highlight": False},
        {"de": "Git / GitHub", "en": "Git / GitHub", "highlight": False}
    ],
    "projekte": [
        {
            "id": "vko",
            "kategorie": "coding",
            "name_de": "Vereinskalender.online",
            "name_en": "Community Event Calendar",
            "url": "https://vereinskalender.online",
            "url_label_de": "vereinskalender.online",
            "url_label_en": "vereinskalender.online",
            "beschreibung_de": "PWA für Vereine und Gemeinden zur Verwaltung und Anzeige von Veranstaltungen. Mehrsprachig (DE/EN), Offline-fähig, Admin-Bereich mit Vereinsverwaltung, Telegram-Bot-Integration, automatische Exportfunktionen.",
            "beschreibung_en": "PWA for clubs and communities to manage and display events. Multilingual (DE/EN), offline-capable, admin area with club management, Telegram bot integration, automatic export functions.",
            "tags": ["FastAPI", "SQLite", "PWA", "Telegram Bot", "nginx"],
            "reihenfolge": 1
        },
        {
            "id": "ai-remote",
            "kategorie": "coding",
            "name_de": "AI Remote Interface",
            "name_en": "AI Remote Interface",
            "url": "",
            "url_label_de": "Internes Tool · Self-hosted",
            "url_label_en": "Internal tool · Self-hosted",
            "beschreibung_de": "Web-Interface zur Fernsteuerung eines lokal laufenden KI-Assistenten über einen selbst-gehosteten Server. Ermöglicht die Nutzung von AI-Unterstützung von überall, ohne die Daten in die Cloud zu senden.",
            "beschreibung_en": "Web interface for remotely controlling a locally running AI assistant via a self-hosted server. Enables AI assistance from anywhere without sending data to the cloud.",
            "tags": ["Flask", "WebSocket", "nginx", "Hetzner", "AI"],
            "reihenfolge": 2
        },
        {
            "id": "dok-auto",
            "kategorie": "coding",
            "name_de": "Dokument-Automatisierung",
            "name_en": "Document Automation",
            "url": "",
            "url_label_de": "Webhook-Service · Self-hosted",
            "url_label_en": "Webhook service · Self-hosted",
            "beschreibung_de": "Automatischer Service der gescannte Dokumente aus einem Dropbox-Ordner per KI analysiert, benennt und kategorisiert. Läuft vollautomatisch als Hintergrundservice auf einem eigenen Server.",
            "beschreibung_en": "Automated service that analyses, names and categorises scanned documents from a Dropbox folder using AI. Runs fully automatically as a background service on a dedicated server.",
            "tags": ["FastAPI", "Dropbox API", "systemd", "Claude API"],
            "reihenfolge": 3
        },
        {
            "id": "task-mgr",
            "kategorie": "coding",
            "name_de": "PKA-Todos",
            "name_en": "Personal Task Manager",
            "url": "",
            "url_label_de": "PWA · Self-hosted",
            "url_label_en": "PWA · Self-hosted",
            "beschreibung_de": "PWA zur persönlichen Aufgabenverwaltung mit Kategorien, Prioritäten, Fälligkeitsdaten und KI-Integration. Dient als zentrales SSOT für persönliche und berufliche Todos.",
            "beschreibung_en": "PWA for personal task management with categories, priorities, due dates and AI integration. Serves as central single source of truth for personal and professional todos.",
            "tags": ["PWA", "JSON SSOT", "GitHub Pages"],
            "reihenfolge": 4
        },
        {
            "id": "rechnung",
            "kategorie": "coding",
            "name_de": "Rechnungserstellung & -verwaltung",
            "name_en": "Invoice Creation & Management",
            "url": "",
            "url_label_de": "Zwei getrennte Apps · Self-hosted",
            "url_label_en": "Two separate apps · Self-hosted",
            "beschreibung_de": "Zwei PWAs: Eine für die automatische Rechnungserstellung aus Word-Vorlagen (mit Variablen-Ersatz, PDF-Ausgabe), eine zweite für die strukturierte Anzeige und Verwaltung aller Rechnungen nach Kunden und Datum.",
            "beschreibung_en": "Two PWAs: one for automatic invoice creation from Word templates (with variable substitution, PDF output), a second for structured display and management of all invoices by customer and date.",
            "tags": ["FastAPI", "python-docx", "PWA", "LibreOffice"],
            "reihenfolge": 5
        },
        {
            "id": "vokabel",
            "kategorie": "coding",
            "name_de": "Vokabeltrainer",
            "name_en": "Vocabulary Trainer",
            "url": "",
            "url_label_de": "PWA · GitHub Pages",
            "url_label_en": "PWA · GitHub Pages",
            "beschreibung_de": "Lernapp für Vokabeln mit mehreren Quiz-Modi (Lückentext, Multiple Choice, Schreiben), Spaced-Repetition-Logik, Offline-Fähigkeit und Statistiken.",
            "beschreibung_en": "Learning app for vocabulary with multiple quiz modes (fill-in-the-blank, multiple choice, writing), spaced repetition logic, offline capability and statistics.",
            "tags": ["PWA", "Service Worker", "Dropbox API", "GitHub Pages"],
            "reihenfolge": 6
        },
        {
            "id": "bewerbung",
            "kategorie": "coding",
            "name_de": "Digitale Bewerbungsseite",
            "name_en": "Digital Application Site",
            "url": "https://fischer-josef.de",
            "url_label_de": "fischer-josef.de",
            "url_label_en": "fischer-josef.de",
            "beschreibung_de": "Diese Seite: Interaktive Bewerbungsmappe mit token-basiertem Zugang, mehrsprachigem Lebenslauf (DE/EN), automatischer PDF-Generierung via KI-Übersetzung, Admin-Bereich und Telegram-Benachrichtigungen.",
            "beschreibung_en": "This site: interactive application portfolio with token-based access, multilingual CV (DE/EN), automatic PDF generation via AI translation, admin area and Telegram notifications.",
            "tags": ["FastAPI", "SQLite", "PWA", "WeasyPrint", "Claude API"],
            "reihenfolge": 7
        }
    ],
    "suche": [
        {"de": "Führungsrolle mit digitalem Anteil – Engineering Services, Digitalisierung, Tech oder Prozessautomatisierung",
         "en": "Leadership role with a digital component – engineering services, digitisation, tech or process automation"},
        {"de": "Vollzeit oder Hybrid – offen für verschiedene Modelle",
         "en": "Full-time or hybrid – open to different models"},
        {"de": "Raum München / Bayern oder remote-freundlich",
         "en": "Munich / Bavaria area or remote-friendly"}
    ],
    "cv": {
        "person": {
            "name": "Josef Fischer",
            "titel_de": "Dipl.-Wirtschaftsingenieur · Strategic Delivery Partner",
            "titel_en": "Graduate Engineer · Strategic Delivery Partner",
            "info_de": "geb. 24.06.1973 · verheiratet · 2 Kinder",
            "info_en": "born 24.06.1973 · married · 2 children",
            "email": "josef.jf.fischer@me.com",
            "wohnort": "Bayerbach",
            "homepage": "https://fischer-josef.de"
        },
        "berufserfahrung": [
            {
                "firma_de": "QuEST Global Engineering Services GmbH, München",
                "firma_en": "QuEST Global Engineering Services GmbH, Munich",
                "zeitraum": "seit 11/2018",
                "rolle_de": "Prokurist | Centre Manager | Strategic Delivery Partner",
                "rolle_en": "Proxy (Prokurist) | Centre Manager | Strategic Delivery Partner",
                "punkte": [
                    {"de": "seit 04/2024: Strategic Delivery Partner BMW VAU – bis zu 320 Mitarbeiter, 28 Mio. $ Umsatz", "en": "Since 04/2024: Strategic Delivery Partner BMW VAU – up to 320 employees, USD 28M revenue"},
                    {"de": "01/2022 – 03/2024: Head of Delivery Germany – regional verantwortlich für Delivery Excellence und Business Development", "en": "01/2022 – 03/2024: Head of Delivery Germany – regional responsibility for delivery excellence and business development"},
                    {"de": "11/2019 – 12/2021: Program Manager für Delivery Units 'Project Management' und 'Electrics, Electronics & Software Services'", "en": "11/2019 – 12/2021: Program Manager for Delivery Units 'Project Management' and 'Electrics, Electronics & Software Services'"},
                    {"de": "11/2018 – 12/2021: Program Manager Delivery Unit 'Project Management' – Projektimplementierung, -durchführung und Aufbau neuer Projekte", "en": "11/2018 – 12/2021: Program Manager Delivery Unit 'Project Management' – project implementation, execution and new project setup"}
                ]
            },
            {
                "firma_de": "DETECH Fahrzeugentwicklung GmbH & Co KG, München",
                "firma_en": "DETECH Fahrzeugentwicklung GmbH & Co KG, Munich",
                "zeitraum": "11/2009 – 10/2018",
                "rolle_de": "Gesellschafter · Vertriebspartner · Leiter Projektmanagement",
                "rolle_en": "Shareholder · Sales Partner · Head of Project Management",
                "punkte": [
                    {"de": "12/2013 – 10/2018: Gesellschafter, Vertriebspartner und Leiter Projektmanagement", "en": "12/2013 – 10/2018: Shareholder, sales partner and head of project management"},
                    {"de": "12/2011 – 11/2013: Vertrieb und Leiter Projektmanagement (80+ Mitarbeiter in Work Package und Body Lease)", "en": "12/2011 – 11/2013: Sales and head of project management (80+ employees in work package and body lease)"},
                    {"de": "11/2009 – 11/2011: Projektingenieur bei BMW AG – Änderungsmanagement im Kundenprozesszentrum (25 Monate)", "en": "11/2009 – 11/2011: Project field engineer at BMW AG – change management in the customer process centre (25 months)"}
                ]
            },
            {
                "firma_de": "ACTANO GmbH, München",
                "firma_en": "ACTANO GmbH, Munich",
                "zeitraum": "01/2005 – 10/2009",
                "rolle_de": "Projektmanagement-Berater · Prozessberater",
                "rolle_en": "Project Management Consultant · Process Consultant",
                "punkte": [
                    {"de": "11/2007 – 10/2009: PM-Berater für BMW AG – Änderungsmanagement und Projektmanagement-Support Antriebssysteme", "en": "11/2007 – 10/2009: PM consultant at BMW AG – change management and project management support, drive systems"},
                    {"de": "01/2005 – 11/2007: Prozessberater für BMW AG – CMMI-Implementierung, Software-Logistik, Projekt SWLdZ (2 Jahre)", "en": "01/2005 – 11/2007: Process consultant at BMW AG – CMMI implementation, software logistics, project SWLdZ (2 years)"}
                ]
            },
            {
                "firma_de": "Josef Fischer, Ingenieurbüro, Bayerbach",
                "firma_en": "Josef Fischer, Engineering Office, Bayerbach",
                "zeitraum": "10/2004 – 01/2005",
                "rolle_de": "Selbstständiger Ingenieurdienstleister",
                "rolle_en": "Self-employed engineering service provider",
                "punkte": [
                    {"de": "Otto Spanner GmbH: Prozessberater für Aufbau einer Produktionslinie (Cabrio-Verdeck)", "en": "Otto Spanner GmbH: process consultant for construction of a convertible folding top production line"},
                    {"de": "DaimlerChrysler via Ingenics AG: Prozessberater – lebenszyklusorientierte Produktion (eigene Methode)", "en": "DaimlerChrysler via Ingenics AG: process consultant – life cycle-oriented production (own method)"}
                ]
            }
        ],
        "ausbildung": [
            {
                "titel_de": "Dipl.-Wirtschaftsingenieur (Univ.) – Schwerpunkt Produktion & Prozesse",
                "titel_en": "Dipl.-Wirtschaftsingenieur (graduate engineer) – focus on Production & Processes",
                "zeitraum": "10/1998 – 12/2004",
                "institution": "Technische Universität Clausthal, Clausthal-Zellerfeld",
                "punkte": [
                    {"de": "Diplomarbeit bei DaimlerChrysler, Rastatt: Fabrikmodell zur monetären Bewertung lebenszyklusorientierter Produktion", "en": "Diploma thesis at DaimlerChrysler, Rastatt: factory model for monetary evaluation of life cycle-oriented production"},
                    {"de": "Praktika: Dr. Ing. h.c. F. Porsche AG Stuttgart (2001) & Porsche / Harley-Davidson Kansas City (2001/02)", "en": "Internships: Dr. Ing. h.c. F. Porsche AG Stuttgart (2001) & Porsche / Harley-Davidson Kansas City (2001/02)"}
                ]
            },
            {
                "titel_de": "Allgemeine Hochschulreife (technischer Zweig)",
                "titel_en": "General university entrance qualification (technical branch)",
                "zeitraum": "09/1996 – 07/1998",
                "institution": "Staatliche Berufsoberschule (BOS), Landshut",
                "punkte": []
            },
            {
                "titel_de": "Ausbildung zum Landwirt · Staatl. gepr. Agronom",
                "titel_en": "Training as a Farmer · State-examined Economist for Agriculture",
                "zeitraum": "09/1989 – 07/1992",
                "institution": "Landshut · seit 10/1994: Bewirtschaftung eigener Land- und Forstwirtschaft",
                "punkte": []
            }
        ],
        "skills_cv": [
            {"de": "Programmmanagement", "en": "Programme Management", "highlight": True},
            {"de": "Business Development", "en": "Business Development", "highlight": True},
            {"de": "AI-assisted Development", "en": "AI-assisted Development", "highlight": True},
            {"de": "Change Management", "en": "Change Management", "highlight": False},
            {"de": "Prozessberatung", "en": "Process Consulting", "highlight": False},
            {"de": "Engineering Services", "en": "Engineering Services", "highlight": False},
            {"de": "Führung (bis 320 MA)", "en": "Leadership (up to 320 staff)", "highlight": False},
            {"de": "Progressive Web Apps", "en": "Progressive Web Apps", "highlight": False},
            {"de": "FastAPI · Python", "en": "FastAPI · Python", "highlight": False},
            {"de": "HTML · CSS · JavaScript", "en": "HTML · CSS · JavaScript", "highlight": False},
            {"de": "Linux · nginx · Server", "en": "Linux · nginx · Server", "highlight": False},
            {"de": "Prozessautomatisierung", "en": "Process Automation", "highlight": False},
            {"de": "SQLite · Git · GitHub", "en": "SQLite · Git · GitHub", "highlight": False}
        ],
        "engagement": [
            {"de": "2021, 2022: Teilnehmer QuEST 'Odyssey' – Top Level Leadership Program", "en": "2021, 2022: Participant in QuEST 'Odyssey' – Top Level Leadership Program"},
            {"de": "SS 2002: Initiator der Gründung einer Studentenberatung in Clausthal-Zellerfeld", "en": "SS 2002: Initiator of founding a student consultancy in Clausthal-Zellerfeld"},
            {"de": "05/2000 – 06/2001: 1. Vorsitzender der VWI-Hochschulgruppe Clausthal e.V.", "en": "05/2000 – 06/2001: 1st Chairman of the VWI-Hochschulgruppe Clausthal e.V."},
            {"de": "Mitglied der Freiwilligen Feuerwehr und eines Trachtenvereins", "en": "Member of the local volunteer fire brigade and a traditional Bavarian club"}
        ],
        "interessen_de": "Familie · Wandern & Laufen · Vibe-Coding · Forstwirtschaft · Feuerwehr · Skifahren · Radfahren · Schwimmen · Lesen",
        "interessen_en": "Family · walking & running · Vibe-Coding · forestry · fire brigade · skiing · cycling · swimming · reading"
    }
}

def _translate_cv_to_en(cv: dict) -> dict:
    """Übersetzt alle DE-Felder im CV via Claude API nach EN. Gibt aktualisiertes CV zurück."""
    if not CLAUDE_KEY:
        return cv
    prompt = (
        "Du bist ein professioneller Übersetzer fuer Lebenslaeufe (DE→EN).\n"
        "Fuelle im folgenden JSON alle *_en-Felder und alle 'en'-Schluessel mit der englischen Uebersetzung des jeweiligen *_de / 'de'-Felds.\n"
        "Firmen- und Institutionsnamen unveraendert lassen.\n"
        "Fachbegriff 'Prokurist' als 'Proxy (Prokurist)' uebersetzen.\n"
        "Professioneller Business-Stil. Gib NUR das aktualisierte JSON zurueck, kein Kommentar.\n\n"
        + json_lib.dumps(cv, ensure_ascii=False)
    )
    resp = http.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": CLAUDE_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 8192,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        text = text.rsplit("```", 1)[0]
    return json_lib.loads(text.strip())

def _merge_cv(existing: dict, updated: dict) -> dict:
    """DE-Felder aus updated übernehmen, EN-Felder aus existing behalten."""
    result = json_lib.loads(json_lib.dumps(existing))  # deep copy
    result["person"].update({k: v for k, v in updated.get("person", {}).items()})
    for key in ("interessen_de",):
        if key in updated:
            result[key] = updated[key]
    for section in ("berufserfahrung", "ausbildung", "skills_cv", "engagement"):
        if section in updated:
            result[section] = updated[section]
    return result

def _get_content() -> dict:
    with db() as con:
        row = con.execute("SELECT value FROM content WHERE key='main'").fetchone()
    if row:
        content = json_lib.loads(row["value"])
        for k, v in _DEFAULT_CONTENT.items():
            if k not in content:
                content[k] = v
        return content
    return _DEFAULT_CONTENT

def gen_token_str() -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        t = f"JF-{''.join(secrets.choice(chars) for _ in range(4))}-{''.join(secrets.choice(chars) for _ in range(4))}"
        with db() as con:
            if not con.execute("SELECT id FROM tokens WHERE token_str=?", (t,)).fetchone():
                return t

def telegram(msg: str):
    if not TG_BOT or not TG_CHAT:
        return
    try:
        http.post(
            f"https://api.telegram.org/bot{TG_BOT}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception:
        pass

def log_event(token_id: int, event_type: str, page: Optional[str], ip: str):
    with db() as con:
        con.execute(
            "INSERT INTO events (token_id, event_type, page, ts, ip) VALUES (?,?,?,?,?)",
            (token_id, event_type, page, datetime.now().isoformat(timespec="seconds"), ip),
        )

def client_ip(request: Request) -> str:
    return request.headers.get("X-Real-IP") or (request.client.host if request.client else "") or ""

def require_firm(request: Request) -> int:
    fid = request.session.get("firm_id")
    if not fid:
        raise HTTPException(401, "Nicht eingeloggt")
    return int(fid)

def require_firm_or_admin(request: Request):
    if not request.session.get("firm_id") and not request.session.get("admin"):
        raise HTTPException(401, "Nicht eingeloggt")

def require_admin(request: Request):
    if not request.session.get("admin"):
        raise HTTPException(401, "Kein Admin-Zugang")

# ---------------------------------------------------------------------------
# Icons (cairosvg, server-seitig)
# ---------------------------------------------------------------------------
_ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-6 -6 36 36">
  <rect x="-6" y="-6" width="36" height="36" fill="#1e3a5f"/>
  <rect x="2" y="7" width="20" height="14" rx="2" stroke="white" stroke-width="1.5" fill="none"/>
  <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" stroke="white" stroke-width="1.5" fill="none" stroke-linecap="round"/>
  <line x1="8" y1="13" x2="16" y2="13" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
  <line x1="8" y1="17" x2="13" y2="17" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
</svg>'''

def _get_icon(size: int) -> Path:
    fname = "apple-touch-icon.png" if size == 180 else f"icon-{size}.png"
    path = ICONS_DIR / fname
    if not path.exists():
        import cairosvg
        ICONS_DIR.mkdir(parents=True, exist_ok=True)
        png = cairosvg.svg2png(bytestring=_ICON_SVG.encode(), output_width=size, output_height=size)
        path.write_bytes(png)
    return path

@app.get("/icon-192.png")
def icon192(): return FileResponse(_get_icon(192), media_type="image/png")

@app.get("/icon-512.png")
def icon512(): return FileResponse(_get_icon(512), media_type="image/png")

@app.get("/apple-touch-icon.png")
def icon_apple(): return FileResponse(_get_icon(180), media_type="image/png")

# ---------------------------------------------------------------------------
# Static Pages
# ---------------------------------------------------------------------------
@app.get("/manifest.json")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json",
                        headers={"Cache-Control": "no-store"})

@app.get("/sw.js")
def sw():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-store"})

@app.get("/", response_class=HTMLResponse)
def landing():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

@app.get("/app/", response_class=HTMLResponse)
def app_page(request: Request):
    if not request.session.get("firm_id") and not request.session.get("admin"):
        return RedirectResponse("/", status_code=302)
    return FileResponse(STATIC_DIR / "app" / "index.html", headers={"Cache-Control": "no-store"})

@app.get("/admin/", response_class=HTMLResponse)
def admin_page(request: Request):
    if not request.session.get("admin"):
        return RedirectResponse("/admin/login", status_code=302)
    return FileResponse(STATIC_DIR / "admin" / "index.html", headers={"Cache-Control": "no-store"})

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page():
    return FileResponse(STATIC_DIR / "admin" / "login.html", headers={"Cache-Control": "no-store"})

@app.get("/assets/vko-logo.svg")
def vko_logo():
    path = ASSETS_DIR / "vko-logo.svg"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/svg+xml")

@app.get("/assets/lebenslauf.pdf")
def lebenslauf_pdf(request: Request):
    require_firm_or_admin(request)
    # Weiterleitung auf generierte DE-Version, Fallback auf originale Datei
    de_path = ASSETS_DIR / "lebenslauf_de.pdf"
    if de_path.exists():
        return FileResponse(de_path, media_type="application/pdf", filename="Lebenslauf_Josef_Fischer_DE.pdf")
    path = ASSETS_DIR / "lebenslauf.pdf"
    if not path.exists():
        raise HTTPException(404, "PDF nicht gefunden")
    return FileResponse(path, media_type="application/pdf", filename="Lebenslauf_Josef_Fischer.pdf")

# ---------------------------------------------------------------------------
# API – Firmen-Auth
# ---------------------------------------------------------------------------
@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    token_str = (body.get("token") or "").strip().upper()
    if not token_str:
        raise HTTPException(400, "Token fehlt")
    with db() as con:
        row = con.execute(
            "SELECT id, firma_name, aktiv FROM tokens WHERE token_str=?", (token_str,)
        ).fetchone()
    if not row or not row["aktiv"]:
        raise HTTPException(401, "Ungültiger oder inaktiver Token")
    request.session["firm_id"] = row["id"]
    request.session["firm_name"] = row["firma_name"]
    log_event(row["id"], "login", None, client_ip(request))
    telegram(f"🔑 <b>{row['firma_name']}</b> hat sich eingeloggt\n{datetime.now().strftime('%d.%m.%Y %H:%M')}")
    return {"ok": True, "firma": row["firma_name"]}

@app.post("/api/logout")
def logout(request: Request):
    request.session.pop("firm_id", None)
    request.session.pop("firm_name", None)
    return {"ok": True}

@app.get("/api/me")
def me(request: Request):
    fid = request.session.get("firm_id")
    if not fid:
        if request.session.get("admin"):
            return {"firm_id": 0, "firm_name": "Admin-Vorschau"}
        raise HTTPException(401)
    return {"firm_id": fid, "firm_name": request.session.get("firm_name")}

@app.post("/api/track")
async def track(request: Request):
    fid = request.session.get("firm_id")
    if not fid:
        return {"ok": False}
    body = await request.json()
    page = (body.get("page") or "")[:100]
    log_event(int(fid), "pageview", page, client_ip(request))
    return {"ok": True}

# ---------------------------------------------------------------------------
# API – Kontakt
# ---------------------------------------------------------------------------
@app.post("/api/kontakt")
async def kontakt(request: Request):
    body = await request.json()
    name      = (body.get("name")      or "").strip()[:100]
    email     = (body.get("email")     or "").strip()[:200]
    nachricht = (body.get("nachricht") or "").strip()[:2000]
    if not email or not nachricht:
        raise HTTPException(400, "E-Mail und Nachricht sind Pflicht")
    firm_id = request.session.get("firm_id")
    with db() as con:
        con.execute(
            "INSERT INTO kontakt_anfragen (name, email, nachricht, ts, token_id) VALUES (?,?,?,?,?)",
            (name, email, nachricht, datetime.now().isoformat(timespec="seconds"), firm_id),
        )
    firma_info = f" (Firma: {request.session.get('firm_name', 'unbekannt')})" if firm_id else ""
    telegram(
        f"📬 <b>Neue Kontaktanfrage</b>{firma_info}\n"
        f"<b>Name:</b> {name or '–'}\n"
        f"<b>E-Mail:</b> {email}\n"
        f"<b>Nachricht:</b>\n{nachricht}"
    )
    return {"ok": True}

# ---------------------------------------------------------------------------
# API – Admin Auth
# ---------------------------------------------------------------------------
@app.post("/api/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    token = (body.get("token") or "").strip()
    if not ADMIN_TOKEN or not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(401, "Falscher Admin-Token")
    request.session["admin"] = True
    return {"ok": True}

@app.post("/api/admin/logout")
def admin_logout(request: Request):
    request.session.pop("admin", None)
    return {"ok": True}

@app.get("/api/admin/me")
def admin_me(request: Request):
    if not request.session.get("admin"):
        raise HTTPException(401)
    return {"ok": True}

# ---------------------------------------------------------------------------
# API – Admin Token-Verwaltung
# ---------------------------------------------------------------------------
@app.get("/api/admin/tokens")
def admin_tokens(request: Request):
    require_admin(request)
    with db() as con:
        rows = con.execute("""
            SELECT t.id, t.token_str, t.firma_name, t.erstellt_am, t.aktiv,
                   COUNT(CASE WHEN e.event_type='login' THEN 1 END) AS login_count,
                   MAX(CASE WHEN e.event_type='login' THEN e.ts END) AS last_login
            FROM tokens t
            LEFT JOIN events e ON e.token_id = t.id
            GROUP BY t.id
            ORDER BY t.id DESC
        """).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/admin/tokens")
async def admin_create_token(request: Request):
    require_admin(request)
    body = await request.json()
    firma = (body.get("firma_name") or "").strip()[:100]
    if not firma:
        raise HTTPException(400, "Firmenname fehlt")
    token_str = gen_token_str()
    with db() as con:
        con.execute(
            "INSERT INTO tokens (token_str, firma_name, erstellt_am) VALUES (?,?,?)",
            (token_str, firma, datetime.now().isoformat(timespec="seconds")),
        )
    return {"ok": True, "token_str": token_str, "firma_name": firma}

@app.patch("/api/admin/tokens/{token_id}")
async def admin_update_token(token_id: int, request: Request):
    require_admin(request)
    body = await request.json()
    with db() as con:
        if "aktiv" in body:
            con.execute("UPDATE tokens SET aktiv=? WHERE id=?", (int(bool(body["aktiv"])), token_id))
        if "firma_name" in body:
            con.execute("UPDATE tokens SET firma_name=? WHERE id=?", (body["firma_name"][:100], token_id))
    return {"ok": True}

# ---------------------------------------------------------------------------
# API – Admin Analytics
# ---------------------------------------------------------------------------
@app.get("/api/admin/events")
def admin_events(request: Request, firma_id: Optional[int] = None, limit: int = 200):
    require_admin(request)
    with db() as con:
        if firma_id:
            rows = con.execute("""
                SELECT e.*, t.firma_name FROM events e
                JOIN tokens t ON t.id = e.token_id
                WHERE e.token_id=? ORDER BY e.ts DESC LIMIT ?
            """, (firma_id, limit)).fetchall()
        else:
            rows = con.execute("""
                SELECT e.*, t.firma_name FROM events e
                JOIN tokens t ON t.id = e.token_id
                ORDER BY e.ts DESC LIMIT ?
            """, (limit,)).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/content")
def get_content():
    return _get_content()

@app.put("/api/admin/content")
async def put_content(request: Request):
    require_admin(request)
    body = await request.json()
    if not all(k in body for k in ("ueber_mich", "skills", "suche")):
        raise HTTPException(400, "Fehlende Felder")
    if "projekte" not in body:
        body["projekte"] = existing.get("projekte", _DEFAULT_CONTENT.get("projekte", []))
    # cv-Key: vorhandene EN-Felder aus bisherigem Stand übernehmen
    existing = _get_content()
    if "cv" not in body:
        body["cv"] = existing.get("cv", _DEFAULT_CONTENT["cv"])
    else:
        body["cv"] = _merge_cv(existing.get("cv", _DEFAULT_CONTENT["cv"]), body["cv"])
    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO content (key, value) VALUES ('main', ?)",
            (json_lib.dumps(body, ensure_ascii=False),)
        )
    return {"ok": True}

@app.post("/api/admin/generate-cv-pdfs")
async def generate_cv_pdfs(request: Request):
    require_admin(request)
    from weasyprint import HTML as WP_HTML
    content = _get_content()
    cv = content.get("cv", _DEFAULT_CONTENT["cv"])
    # DE → EN übersetzen und EN-Felder in DB zurückschreiben
    cv = _translate_cv_to_en(cv)
    content["cv"] = cv
    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO content (key, value) VALUES ('main', ?)",
            (json_lib.dumps(content, ensure_ascii=False),)
        )
    # Beide PDFs generieren
    tmpl = _jinja.get_template("cv_print.html")
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for lang in ("de", "en"):
        html = tmpl.render(cv=cv, lang=lang, ueber_mich=content.get("ueber_mich", {}))
        pdf = WP_HTML(string=html, base_url=str(BASE)).write_pdf()
        (ASSETS_DIR / f"lebenslauf_{lang}.pdf").write_bytes(pdf)
    return {"ok": True, "files": ["lebenslauf_de.pdf", "lebenslauf_en.pdf"]}

@app.get("/assets/lebenslauf_de.pdf")
def lebenslauf_de_pdf(request: Request):
    require_firm_or_admin(request)
    path = ASSETS_DIR / "lebenslauf_de.pdf"
    if not path.exists():
        raise HTTPException(404, "PDF noch nicht generiert – Admin: Lebenslauf-PDFs generieren")
    return FileResponse(path, media_type="application/pdf", filename="Lebenslauf_Josef_Fischer_DE.pdf")

@app.get("/assets/lebenslauf_en.pdf")
def lebenslauf_en_pdf(request: Request):
    require_firm_or_admin(request)
    path = ASSETS_DIR / "lebenslauf_en.pdf"
    if not path.exists():
        raise HTTPException(404, "PDF noch nicht generiert – Admin: Lebenslauf-PDFs generieren")
    return FileResponse(path, media_type="application/pdf", filename="CV_Josef_Fischer_EN.pdf")

@app.get("/api/admin/kontakt")
def admin_kontakt_list(request: Request):
    require_admin(request)
    with db() as con:
        rows = con.execute("""
            SELECT k.*, t.firma_name FROM kontakt_anfragen k
            LEFT JOIN tokens t ON t.id = k.token_id
            ORDER BY k.ts DESC
        """).fetchall()
    return [dict(r) for r in rows]
