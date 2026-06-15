"""
Bewerbungsseite Josef Fischer – Backend
FastAPI + SQLite + Telegram | Port 5004
"""
import os, sqlite3, secrets, string
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
import requests as http

BASE       = Path(__file__).parent
DB_PATH    = BASE / "bewerbung.db"
ICONS_DIR  = BASE / "icons"
STATIC_DIR = BASE / "static"
ASSETS_DIR = BASE / "assets"

ADMIN_TOKEN = os.environ.get("BEWERBUNG_ADMIN_TOKEN", "")
TG_BOT      = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = os.environ.get("TELEGRAM_CHAT_ID", "")
SECRET_KEY  = os.environ.get("BEWERBUNG_SECRET_KEY", secrets.token_hex(32))
HTTPS_ONLY  = os.environ.get("HTTPS_ONLY", "true").lower() == "true"

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
    if not request.session.get("firm_id"):
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
    require_firm(request)
    path = ASSETS_DIR / "lebenslauf.pdf"
    if not path.exists():
        raise HTTPException(404, "PDF nicht gefunden")
    return FileResponse(path, media_type="application/pdf",
                        filename="Lebenslauf_Josef_Fischer.pdf")

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
    request.session.clear()
    return {"ok": True}

@app.get("/api/me")
def me(request: Request):
    fid = request.session.get("firm_id")
    if not fid:
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
