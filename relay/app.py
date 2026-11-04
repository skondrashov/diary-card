import hashlib
import re
import secrets
import sqlite3
import string
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

DB_PATH = Path(__file__).parent / "relay.db"
PREFIXES = string.ascii_lowercase
PREFIX_ROTATION_SECONDS = 7 * 86400
SUFFIX_CHARS = string.ascii_lowercase + string.digits
SUFFIX_LEN = 4
MIN_TTL = 60
DEFAULT_TTL = 30 * 86400
MAX_TTL = 90 * 86400
MAX_PAYLOAD = 100_000
B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS links ("
        "token TEXT PRIMARY KEY, "
        "payload TEXT NOT NULL, "
        "created_at REAL NOT NULL, "
        "expires_at REAL NOT NULL)"
    )
    # Links created before edit keys existed have NULL here and can't be updated, only replaced.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(links)")}
    if "edit_key_hash" not in cols:
        conn.execute("ALTER TABLE links ADD COLUMN edit_key_hash TEXT")
        conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def current_prefix():
    return PREFIXES[int(time.time() // PREFIX_ROTATION_SECONDS) % len(PREFIXES)]


def generate_token():
    prefix = current_prefix()
    suffix = "".join(secrets.choice(SUFFIX_CHARS) for _ in range(SUFFIX_LEN))
    return prefix + suffix


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def cleanup(conn):
    conn.execute("DELETE FROM links WHERE expires_at < ?", (time.time(),))
    conn.commit()


def validate_payload(payload: str):
    if not payload or len(payload) > MAX_PAYLOAD:
        raise HTTPException(400, "Payload empty or too large")
    if not B64URL_RE.match(payload):
        raise HTTPException(400, "Payload must be base64url")


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


class CreateRequest(BaseModel):
    payload: str
    ttl: int = DEFAULT_TTL


class UpdateRequest(BaseModel):
    payload: str
    ttl: int = DEFAULT_TTL
    edit_key: str


@app.post("/api/relay")
async def create_link(req: CreateRequest):
    validate_payload(req.payload)
    ttl = max(MIN_TTL, min(req.ttl, MAX_TTL))
    now = time.time()
    expires_at = now + ttl
    # The edit key is the only credential that can overwrite a link. The token is in the URL the
    # recipient holds, so it can't be. Only the hash is stored.
    edit_key = secrets.token_urlsafe(24)

    with get_db() as conn:
        cleanup(conn)
        for _ in range(5):
            token = generate_token()
            try:
                conn.execute(
                    "INSERT INTO links (token, payload, created_at, expires_at, edit_key_hash) VALUES (?, ?, ?, ?, ?)",
                    (token, req.payload, now, expires_at, hash_key(edit_key)),
                )
                conn.commit()
                return {"token": token, "edit_key": edit_key, "expires_at": iso(expires_at)}
            except sqlite3.IntegrityError:
                continue

    raise HTTPException(503, "Token generation failed")


@app.put("/api/relay/{token}")
async def update_link(token: str, req: UpdateRequest):
    """Replace a link's payload in place and restart its TTL. Same URL, new contents."""
    validate_payload(req.payload)
    ttl = max(MIN_TTL, min(req.ttl, MAX_TTL))
    now = time.time()

    with get_db() as conn:
        row = conn.execute(
            "SELECT expires_at, edit_key_hash FROM links WHERE token = ?", (token,)
        ).fetchone()
        if not row or row[0] < now:
            raise HTTPException(404, detail="expired")
        if not row[1] or not secrets.compare_digest(row[1], hash_key(req.edit_key)):
            raise HTTPException(403, detail="bad edit key")
        expires_at = now + ttl
        conn.execute(
            "UPDATE links SET payload = ?, expires_at = ? WHERE token = ?",
            (req.payload, expires_at, token),
        )
        conn.commit()

    return {"token": token, "expires_at": iso(expires_at)}


@app.get("/api/relay/health")
async def health():
    with get_db() as conn:
        cleanup(conn)
        count = conn.execute("SELECT COUNT(*) FROM links WHERE expires_at > ?", (time.time(),)).fetchone()[0]
    return {"status": "ok", "active_links": count}


@app.get("/api/relay/{token}")
async def get_link(token: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT payload, expires_at FROM links WHERE token = ?", (token,)
        ).fetchone()

    if not row or row[1] < time.time():
        raise HTTPException(404, detail="expired")

    return {"payload": row[0], "expires_at": iso(row[1])}
