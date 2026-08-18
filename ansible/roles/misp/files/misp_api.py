#!/usr/bin/env python3
"""MSSP MISP REST bridge — IOC store + restSearch-compatible API.

Control-plane client: backend-api/app/services/misp_client.py
API key is read from MISP_API_KEY_FILE (generated on the host, never in Git).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DB = Path(os.environ.get("MISP_DB", "/opt/mssp-misp/data/iocs.sqlite3"))
KEY_FILE = Path(os.environ.get("MISP_API_KEY_FILE", "/opt/mssp-misp/secrets/admin_key"))
BIND = os.environ.get("MISP_BIND", "0.0.0.0")
PORT = int(os.environ.get("MISP_PORT", "8080"))


def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS attributes(
        id INTEGER PRIMARY KEY, type TEXT, value TEXT, category TEXT,
        comment TEXT, to_ids INTEGER, timestamp INTEGER, event_id INTEGER,
        UNIQUE(type, value))"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY, info TEXT, threat_level_id INTEGER, timestamp INTEGER)"""
    )
    n = conn.execute("SELECT count(*) FROM events").fetchone()[0]
    if n == 0:
        conn.execute(
            "INSERT INTO events(id,info,threat_level_id,timestamp) VALUES(1,'MSSP threat feed',2,?)",
            (int(time.time()),),
        )
        conn.commit()
    return conn


def _authorized(headers) -> bool:
    expected = KEY_FILE.read_text().strip() if KEY_FILE.exists() else ""
    authh = headers.get("Authorization") or headers.get("authorization") or ""
    if authh.lower().startswith("bearer "):
        authh = authh[7:].strip()
    return bool(expected) and authh.strip() == expected


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/health", "/servers/getVersion"):
            self._json(200, {"version": "2.4.mssp", "status": "ok", "pymisp_compatible": True})
            return
        if not _authorized(self.headers):
            self._json(401, {"message": "unauthorized"})
            return
        if path == "/attributes/describeTypes":
            self._json(
                200,
                {
                    "result": {
                        "types": [
                            "ip-dst",
                            "ip-src",
                            "domain",
                            "hostname",
                            "md5",
                            "sha1",
                            "sha256",
                            "url",
                        ]
                    }
                },
            )
            return
        self._json(404, {"message": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not _authorized(self.headers):
            self._json(401, {"message": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode() or "{}")
        except Exception:
            payload = {}
        if path in ("/attributes/restSearch", "/attributes/restSearch/"):
            conn = db()
            rows = conn.execute(
                "SELECT id,type,value,category,comment,to_ids,timestamp,event_id FROM attributes WHERE to_ids=1"
            ).fetchall()
            conn.close()
            attrs = [
                {
                    "id": str(row[0]),
                    "type": row[1],
                    "value": row[2],
                    "category": row[3],
                    "comment": row[4] or "",
                    "to_ids": bool(row[5]),
                    "timestamp": str(row[6]),
                    "event_id": str(row[7]),
                }
                for row in rows
            ]
            value = payload.get("value")
            if isinstance(payload.get("Attribute"), dict):
                value = value or payload["Attribute"].get("value")
            if value:
                needle = str(value).lower()
                attrs = [a for a in attrs if needle in a["value"].lower()]
            self._json(200, {"response": {"Attribute": attrs}})
            return
        if path in ("/events/restSearch", "/events/index"):
            self._json(
                200,
                {
                    "response": [
                        {
                            "Event": {
                                "id": "1",
                                "info": "MSSP threat feed",
                                "threat_level_id": "2",
                                "Attribute": [],
                            }
                        }
                    ]
                },
            )
            return
        if path == "/attributes/add":
            attr = payload.get("Attribute") or payload
            conn = db()
            conn.execute(
                "INSERT OR REPLACE INTO attributes(type,value,category,comment,to_ids,timestamp,event_id) VALUES(?,?,?,?,1,?,1)",
                (
                    attr.get("type") or "other",
                    attr.get("value") or "",
                    attr.get("category") or "Network activity",
                    attr.get("comment") or "",
                    int(time.time()),
                ),
            )
            conn.commit()
            conn.close()
            self._json(200, {"Attribute": attr})
            return
        self._json(404, {"message": "not found"})


if __name__ == "__main__":
    db().close()
    print(f"MISP bridge on {BIND}:{PORT}", flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
