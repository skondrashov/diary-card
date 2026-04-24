import re
import secrets
import sqlite3
import string
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

DB_PATH = Path(__file__).parent / "relay.db"
PREFIXES = string.ascii_lowercase
EPOCH_SECONDS = 7 * 86400
SUFFIX_CHARS = string.ascii_lowercase + string.digits
SUFFIX_LEN = 4
DEFAULT_TTL = 30 * 86400
MAX_TTL = 90 * 86400
MAX_PAYLOAD = 100_000
B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


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
    return conn


def current_prefix():
    return PREFIXES[int(time.time() // EPOCH_SECONDS) % len(PREFIXES)]


def generate_token():
    prefix = current_prefix()
    suffix = "".join(secrets.choice(SUFFIX_CHARS) for _ in range(SUFFIX_LEN))
    return prefix + suffix


def cleanup(conn):
    conn.execute("DELETE FROM links WHERE expires_at < ?", (time.time(),))
    conn.commit()


class CreateRequest(BaseModel):
    payload: str
    ttl: int = DEFAULT_TTL


@app.post("/api/relay")
async def create_link(req: CreateRequest):
    if not req.payload or len(req.payload) > MAX_PAYLOAD:
        raise HTTPException(400, "Payload empty or too large")
    if not B64URL_RE.match(req.payload):
        raise HTTPException(400, "Payload must be base64url")

    ttl = max(60, min(req.ttl, MAX_TTL))
    now = time.time()
    expires_at = now + ttl

    conn = get_db()
    cleanup(conn)

    for _ in range(5):
        token = generate_token()
        try:
            conn.execute(
                "INSERT INTO links (token, payload, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, req.payload, now, expires_at),
            )
            conn.commit()
            conn.close()
            return {
                "token": token,
                "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
            }
        except sqlite3.IntegrityError:
            continue

    conn.close()
    raise HTTPException(503, "Token generation failed")


@app.get("/api/relay/health")
async def health():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM links WHERE expires_at > ?", (time.time(),)).fetchone()[0]
    conn.close()
    return {"status": "ok", "active_links": count}


@app.get("/api/relay/{token}")
async def get_link(token: str):
    conn = get_db()
    row = conn.execute(
        "SELECT payload, expires_at FROM links WHERE token = ?", (token,)
    ).fetchone()
    conn.close()

    if not row or row[1] < time.time():
        raise HTTPException(404, detail="expired")

    return {
        "payload": row[0],
        "expires_at": datetime.fromtimestamp(row[1], tz=timezone.utc).isoformat(),
    }
