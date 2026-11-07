#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIVAZ — servidor da cópia local.

* Serve os arquivos estáticos originais em public/ sem alteração (UI idêntica).
* Fornece banco de dados real (SQLite), login por sessão e API de sincronismo.
* Zero dependências externas: apenas biblioteca padrão do Python 3.

Uso:  python3 server.py            (porta 3000)
      PORT=8080 python3 server.py (outra porta)
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, "public")
DATA = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA, "vivaz.db")
PORT = int(os.environ.get("PORT", "3000"))

COOKIE = "vivaz_session"
SESSION_DAYS = 30
MAX_BODY = 12 * 1024 * 1024

ADMIN_EMAIL = os.environ.get("VIVAZ_ADMIN_EMAIL", "admin@vivaz.local")
ADMIN_PASSWORD = os.environ.get("VIVAZ_ADMIN_PASSWORD", "Vivaz@2026")
ADMIN_NAME = os.environ.get("VIVAZ_ADMIN_NAME", "Marina Almeida")


def utcnow():
    return datetime.now(timezone.utc)


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def connect():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def hash_password(password, salt_hex=None):
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 200_000
    ).hex()
    return salt.hex(), digest


def init_db():
    os.makedirs(DATA, exist_ok=True)
    con = connect()
    con.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS users (
          id             INTEGER PRIMARY KEY AUTOINCREMENT,
          email          TEXT NOT NULL UNIQUE COLLATE NOCASE,
          name           TEXT NOT NULL,
          role           TEXT NOT NULL DEFAULT 'corretor',
          salt           TEXT NOT NULL,
          password_hash  TEXT NOT NULL,
          created_at     TEXT NOT NULL,
          last_login_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
          token       TEXT PRIMARY KEY,
          user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at  TEXT NOT NULL,
          expires_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

        -- Uma linha por coleção do estado da aplicação (imóveis, negócios,
        -- contatos, leads, agenda, chat, configurações, ...).
        CREATE TABLE IF NOT EXISTS app_state (
          collection  TEXT PRIMARY KEY,
          payload     TEXT NOT NULL,
          updated_at  TEXT NOT NULL,
          updated_by  INTEGER REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
          id          INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id     INTEGER,
          action      TEXT NOT NULL,
          detail      TEXT,
          created_at  TEXT NOT NULL
        );
    """)
    if con.execute("SELECT id FROM users LIMIT 1").fetchone() is None:
        salt, digest = hash_password(ADMIN_PASSWORD)
        con.execute(
            "INSERT INTO users(email,name,role,salt,password_hash,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (ADMIN_EMAIL, ADMIN_NAME, "admin", salt, digest, stamp(utcnow())),
        )

    # Primeira execução: popula o banco com o estado inicial autêntico do app
    # (extraído do próprio site via "Redefinir dados de demonstração").
    seed_path = os.path.join(DATA, "seed.json")
    if (con.execute("SELECT COUNT(*) FROM app_state").fetchone()[0] == 0
            and os.path.isfile(seed_path)):
        with open(seed_path, "r", encoding="utf-8") as handle:
            seed = json.load(handle)
        owner = con.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]
        now = stamp(utcnow())
        for key, value in seed.items():
            con.execute(
                "INSERT INTO app_state(collection,payload,updated_at,updated_by) "
                "VALUES(?,?,?,?) ON CONFLICT(collection) DO UPDATE SET "
                "payload=excluded.payload, updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), now, owner),
            )
        con.execute(
            "INSERT INTO audit_log(user_id,action,detail,created_at) "
            "VALUES(?,?,?,?)",
            (owner, "seed:inicial", "%d coleções" % len(seed), now),
        )
    con.commit()
    con.close()


def public_user(row):
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
    }


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC, **kwargs)

    def log_message(self, fmt, *args):
        if os.environ.get("VIVAZ_QUIET"):
            return
        super().log_message(fmt, *args)

    # ---------- utilidades ----------
    def _cors(self):
        # O preview do Arena roda dentro de um iframe de outra origem.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def end_headers(self):
        self._cors()
        super().end_headers()

    def _json(self, code, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if size <= 0 or size > MAX_BODY:
            return None
        raw = self.rfile.read(size)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def _token(self):
        # Preferimos o token Bearer: cookies são bloqueados em iframe de
        # terceiros (é assim que o Live Preview do Arena incorpora o app).
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and len(auth) > 7:
            return auth[7:].strip()
        try:
            jar = SimpleCookie()
            jar.load(self.headers.get("Cookie", ""))
            if COOKIE in jar:
                return jar[COOKIE].value
        except Exception:
            pass
        return None

    def _user(self):
        token = self._token()
        if not token:
            return None
        con = connect()
        row = con.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > ?",
            (token, stamp(utcnow())),
        ).fetchone()
        con.close()
        return row

    def _auth(self):
        user = self._user()
        if user is None:
            self._json(401, {"error": "Não autenticado. Faça login."})
        return user

    # ---------- API ----------
    def _api(self, method):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/api/health" and method == "GET":
            con = connect()
            tables = [
                r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            counts = {
                t: con.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                for t in tables
            }
            con.close()
            return self._json(200, {
                "ok": True, "app": "vivaz", "database": DB_PATH,
                "tables": counts,
            })

        if path == "/api/session" and method == "GET":
            # Sempre 200: evita ruído de console no carregamento inicial.
            user = self._user()
            return self._json(200, {
                "authenticated": user is not None,
                "user": public_user(user) if user else None,
            })

        if path == "/api/me" and method == "GET":
            user = self._user()
            if user is None:
                return self._json(401, {"error": "Não autenticado."})
            return self._json(200, {"user": public_user(user)})

        if path == "/api/login" and method == "POST":
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "JSON inválido."})
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            con = connect()
            row = con.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
            ).fetchone()
            if row is None:
                con.close()
                return self._json(401, {"error": "E-mail ou senha incorretos."})
            _, digest = hash_password(password, row["salt"])
            if not hmac.compare_digest(digest, row["password_hash"]):
                con.close()
                return self._json(401, {"error": "E-mail ou senha incorretos."})
            token = secrets.token_urlsafe(32)
            created = utcnow()
            expires = created + timedelta(days=SESSION_DAYS)
            con.execute(
                "INSERT INTO sessions(token,user_id,created_at,expires_at) "
                "VALUES(?,?,?,?)",
                (token, row["id"], stamp(created), stamp(expires)),
            )
            con.execute("UPDATE users SET last_login_at=? WHERE id=?",
                        (stamp(created), row["id"]))
            con.execute(
                "INSERT INTO audit_log(user_id,action,detail,created_at) "
                "VALUES(?,?,?,?)",
                (row["id"], "login",
                 (self.headers.get("User-Agent") or "")[:200], stamp(created)),
            )
            con.commit()
            user = public_user(row)
            con.close()
            cookie = (
                "%s=%s; Path=/; HttpOnly; Secure; SameSite=None; "
                "Partitioned; Max-Age=%d"
                % (COOKIE, token, SESSION_DAYS * 86400)
            )
            return self._json(200, {
                "ok": True, "user": user, "token": token
            }, [("Set-Cookie", cookie)])

        if path == "/api/logout" and method == "POST":
            token = self._token()
            if token:
                con = connect()
                con.execute("DELETE FROM sessions WHERE token=?", (token,))
                con.commit()
                con.close()
            return self._json(200, {"ok": True}, [
                ("Set-Cookie", "%s=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
                 % COOKIE),
            ])

        if path == "/api/state" and method == "GET":
            user = self._auth()
            if user is None:
                return
            con = connect()
            rows = con.execute(
                "SELECT collection,payload FROM app_state ORDER BY collection"
            ).fetchall()
            con.close()
            state = {}
            for row in rows:
                try:
                    state[row["collection"]] = json.loads(row["payload"])
                except Exception:
                    state[row["collection"]] = row["payload"]
            return self._json(200, {"state": state or None,
                                    "user": public_user(user)})

        if path == "/api/state" and method == "PUT":
            user = self._auth()
            if user is None:
                return
            data = self._body()
            if not isinstance(data, dict) or not data:
                return self._json(400, {"error": "Estado inválido."})
            now = stamp(utcnow())
            con = connect()
            con.execute("DELETE FROM app_state")
            for key, value in data.items():
                payload = json.dumps(value, ensure_ascii=False)
                con.execute(
                    "INSERT INTO app_state(collection,payload,updated_at,updated_by) "
                    "VALUES(?,?,?,?)",
                    (str(key)[:120], payload, now, user["id"]),
                )
            con.execute(
                "INSERT INTO audit_log(user_id,action,detail,created_at) "
                "VALUES(?,?,?,?)",
                (user["id"], "state:sync", "%d coleções" % len(data), now),
            )
            con.commit()
            con.close()
            return self._json(200, {"ok": True, "collections": len(data)})

        if path == "/api/schema" and method == "GET":
            if self._auth() is None:
                return
            con = connect()
            info = {}
            for row in con.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ):
                info[row["name"]] = {
                    "rows": con.execute(
                        "SELECT COUNT(*) FROM " + row["name"]
                    ).fetchone()[0],
                    "sql": row["sql"],
                }
            con.close()
            return self._json(200, {"tables": info})

        if path == "/api/users" and method == "GET":
            if self._auth() is None:
                return
            con = connect()
            rows = con.execute(
                "SELECT id,email,name,role,created_at,last_login_at "
                "FROM users ORDER BY id"
            ).fetchall()
            con.close()
            return self._json(200, {"users": [dict(r) for r in rows]})

        if path == "/api/users" and method == "POST":
            user = self._auth()
            if user is None:
                return
            if user["role"] != "admin":
                return self._json(403, {"error": "Somente administradores."})
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "JSON inválido."})
            email = str(data.get("email", "")).strip().lower()
            name = str(data.get("name", "")).strip()
            password = str(data.get("password", ""))
            role = str(data.get("role", "corretor"))
            if not email or "@" not in email or len(password) < 8:
                return self._json(400, {
                    "error": "Informe e-mail válido e senha com 8+ caracteres."
                })
            salt, digest = hash_password(password)
            con = connect()
            try:
                con.execute(
                    "INSERT INTO users(email,name,role,salt,password_hash,created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (email, name or email.split("@")[0],
                     role if role in ("admin", "gerente", "corretor") else "corretor",
                     salt, digest, stamp(utcnow())),
                )
                con.commit()
            except sqlite3.IntegrityError:
                con.close()
                return self._json(409, {"error": "E-mail já cadastrado."})
            con.close()
            return self._json(201, {"ok": True, "email": email})

        return self._json(404, {"error": "Rota não encontrada."})

    # ---------- dispatch ----------
    def do_GET(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self._api("GET")
        return super().do_GET()

    def do_HEAD(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self._json(405, {"error": "Método não permitido."})
        return super().do_HEAD()

    def do_POST(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self._api("POST")
        return self._json(405, {"error": "Método não permitido."})

    def do_PUT(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self._api("PUT")
        return self._json(405, {"error": "Método não permitido."})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    print("VIVAZ em http://0.0.0.0:%d  |  banco: %s" % (PORT, DB_PATH))
    print("Login padrão: %s / %s" % (ADMIN_EMAIL, ADMIN_PASSWORD))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
