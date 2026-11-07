#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VIVAZ — servidor profissional, multi-tenant individual, backend Supabase.

Isolamento: cada usuário só acessa a PRÓPRIA carteira. Quem garante isso é o
RLS do Postgres (owner_id = auth.uid()), porque as chamadas de estado usam o
access_token do usuário no PostgREST — não a service_role. Admin é a única
exceção (policy vivaz_is_admin) e enxerga todas as carteiras pelo painel.

  * login   -> Supabase Auth (grant_type=password + refresh automático)
  * estado  -> /rest/v1/vivaz_state?owner_id=eq.<uid> com RLS
  * sync    -> RPC vivaz_replace_state (só a carteira do dono + auditoria)
  * equipe  -> Auth Admin API + vivaz_profiles (somente admin)
  * fotos   -> Supabase Storage (URL pública injetada no index)

A service_role fica SOMENTE aqui. O navegador recebe um token Bearer opaco.
"""
import json
import os
import re
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, "public")
DATA = os.path.join(ROOT, "data")
SESSIONS_DB = os.path.join(DATA, "supabase_sessions.db")
PORT = int(os.environ.get("PORT", "3000"))
MAX_BODY = 12 * 1024 * 1024
COOKIE = "vivaz_session"
SESSION_DAYS = 30

ENV = {}
_env_path = os.path.join(ROOT, ".env")
if os.path.isfile(_env_path):
    for _line in open(_env_path, encoding="utf-8"):
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.strip().split("=", 1)
            ENV[_k] = _v


def cfg(name, default=""):
    return os.environ.get(name) or ENV.get(name) or default


URL = cfg("SUPABASE_URL").rstrip("/")
ANON = cfg("SUPABASE_ANON_KEY")
SERVICE = cfg("SUPABASE_SERVICE_ROLE_KEY")
BUCKET = cfg("SUPABASE_BUCKET", "vivaz-fotos")
PHOTO_BASE = (URL + "/storage/v1/object/public/" + BUCKET +
              "/vivaz/photos/175-vivaz/")
ADMIN_EMAIL = cfg("VIVAZ_ADMIN_EMAIL", "admin@vivaz.local")
ADMIN_PASSWORD = cfg("VIVAZ_ADMIN_PASSWORD", "Vivaz@2026")

if not URL or not ANON or not SERVICE:
    raise SystemExit("Configure .env: SUPABASE_URL, SUPABASE_ANON_KEY, "
                     "SUPABASE_SERVICE_ROLE_KEY")


def utcnow():
    return datetime.now(timezone.utc)


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# --------------------------------------------------------------------------
# Cliente Supabase (stdlib)
# --------------------------------------------------------------------------
def sb(method, path, body=None, key=None, apikey=None, extra=None, timeout=30):
    """key = Bearer usado; apikey = chave do header apikey (padrão = key)."""
    bearer = key or SERVICE
    headers = {
        "apikey": apikey or bearer,
        "Authorization": "Bearer " + bearer,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    headers.update(extra or {})
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            parsed = (json.loads(raw) if raw and
                      r.headers.get("content-type", "").startswith("application/json")
                      else raw.decode("utf-8", "replace"))
            return r.status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode("utf-8", "replace")
    except Exception as e:
        return 0, {"error": str(e)}


# --------------------------------------------------------------------------
# Sessões locais (só tokens; dados ficam no Supabase)
# --------------------------------------------------------------------------
def sessions():
    os.makedirs(DATA, exist_ok=True)
    con = sqlite3.connect(SESSIONS_DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS sessions (
        token          TEXT PRIMARY KEY,
        user_id        TEXT NOT NULL,
        email          TEXT NOT NULL,
        name           TEXT NOT NULL,
        role           TEXT NOT NULL,
        access_token   TEXT,
        refresh_token  TEXT,
        sb_expires_at  TEXT,
        created_at     TEXT NOT NULL,
        expires_at     TEXT NOT NULL
    )""")
    cols = {r[1] for r in con.execute("PRAGMA table_info(sessions)")}
    for col, ddl in (("sb_expires_at", "ALTER TABLE sessions ADD COLUMN sb_expires_at TEXT"),
                     ("access_token", "ALTER TABLE sessions ADD COLUMN access_token TEXT"),
                     ("refresh_token", "ALTER TABLE sessions ADD COLUMN refresh_token TEXT")):
        if col not in cols:
            con.execute(ddl)
    con.commit()
    return con


def public_user(row):
    return {"id": row["user_id"], "email": row["email"],
            "name": row["name"], "role": row["role"]}


def user_access(row):
    """access_token do usuário, renovado automaticamente via refresh_token."""
    exp = row["sb_expires_at"] or ""
    if exp and exp > stamp(utcnow()):
        return row["access_token"]
    code, data = sb("POST", "/auth/v1/token?grant_type=refresh_token",
                    {"refresh_token": row["refresh_token"]},
                    key=ANON, apikey=ANON)
    if code == 200 and isinstance(data, dict) and data.get("access_token"):
        new_exp = stamp(utcnow() + timedelta(
            seconds=max(60, int(data.get("expires_in", 3600)) - 120)))
        con = sessions()
        con.execute("UPDATE sessions SET access_token=?, refresh_token=?, "
                    "sb_expires_at=? WHERE token=?",
                    (data["access_token"], data.get("refresh_token") or
                     row["refresh_token"], new_exp, row["token"]))
        con.commit()
        con.close()
        return data["access_token"]
    return row["access_token"]


def user_sb(row, method, path, body=None, extra=None, timeout=45):
    """Chamada ao PostgREST/Auth como o usuário logado => RLS ativo."""
    return sb(method, path, body, key=user_access(row), apikey=ANON,
              extra=extra, timeout=timeout)


def profile_of(uid):
    code, prof = sb("GET", "/rest/v1/vivaz_profiles?id=eq." +
                    urllib.parse.quote(uid) +
                    "&select=id,name,role,status,phone,created_at,last_login_at")
    return prof[0] if isinstance(prof, list) and prof else {}


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC, **kwargs)

    def log_message(self, fmt, *args):
        if os.environ.get("VIVAZ_QUIET"):
            return
        super().log_message(fmt, *args)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, PUT, PATCH, OPTIONS")
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
        for k, v in headers or []:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if size <= 0 or size > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(size).decode("utf-8"))
        except Exception:
            return None

    def _token(self):
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
        con = sessions()
        row = con.execute("SELECT * FROM sessions WHERE token=? AND expires_at>?",
                          (token, stamp(utcnow()))).fetchone()
        con.close()
        return row

    def _auth(self):
        row = self._user()
        if row is None:
            self._json(401, {"error": "Não autenticado. Faça login."})
        return row

    def _admin(self):
        row = self._auth()
        if row is None:
            return None
        if row["role"] != "admin":
            self._json(403, {"error": "Somente administradores."})
            return None
        return row

    def _serve_index(self):
        with open(os.path.join(PUBLIC, "index.html"), "rb") as fh:
            html = fh.read()
        needle = b'<script type="module" src="/boot.js"></script>'
        inject = ("<script>window.__VIVAZ_PHOTO_BASE__=%s;</script>"
                  % json.dumps(PHOTO_BASE)).encode("utf-8")
        html = html.replace(needle, inject + needle)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html)

    # ---------- API ----------
    def _api(self, method):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/health" and method == "GET":
            code, state = sb("GET", "/rest/v1/vivaz_state?select=owner_id")
            code2, profiles = sb("GET", "/rest/v1/vivaz_profiles?select=id,status")
            code3, audit = sb("GET", "/rest/v1/vivaz_audit?select=id")
            donos = len({r["owner_id"] for r in state}) if isinstance(state, list) else 0
            return self._json(200 if code == 200 else 502, {
                "ok": code == 200, "app": "vivaz", "backend": "supabase",
                "mode": "individual", "database": URL, "storage": BUCKET,
                "tables": {
                    "vivaz_state": len(state) if isinstance(state, list) else 0,
                    "carteiras": donos,
                    "vivaz_profiles": len(profiles) if isinstance(profiles, list) else 0,
                    "vivaz_audit": len(audit) if isinstance(audit, list) else 0,
                },
            })

        if path == "/api/session" and method == "GET":
            row = self._user()
            return self._json(200, {
                "authenticated": row is not None,
                "user": public_user(row) if row else None,
                "backend": "supabase", "mode": "individual",
            })

        if path == "/api/me" and method == "GET":
            row = self._user()
            if row is None:
                return self._json(401, {"error": "Não autenticado."})
            return self._json(200, {"user": public_user(row),
                                    "profile": profile_of(row["user_id"])})

        if path == "/api/login" and method == "POST":
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "JSON inválido."})
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            code, auth = sb("POST", "/auth/v1/token?grant_type=password",
                            {"email": email, "password": password},
                            key=ANON, apikey=ANON)
            if code != 200 or not isinstance(auth, dict) or "access_token" not in auth:
                return self._json(401, {"error": "E-mail ou senha incorretos."})
            uid = (auth.get("user") or {}).get("id", "")
            prof = profile_of(uid)
            if prof.get("status", "ativo") != "ativo":
                return self._json(403, {"error": "Conta desativada. Fale com o administrador."})
            meta = (auth.get("user") or {}).get("user_metadata") or {}
            name = prof.get("name") or meta.get("name", "Marina Almeida")
            role = prof.get("role") or meta.get("role", "corretor")
            token = secrets.token_urlsafe(32)
            created = utcnow()
            sb_exp = stamp(created + timedelta(
                seconds=max(60, int(auth.get("expires_in", 3600)) - 120)))
            con = sessions()
            con.execute("DELETE FROM sessions WHERE expires_at<=?", (stamp(created),))
            con.execute(
                "INSERT INTO sessions(token,user_id,email,name,role,access_token,"
                "refresh_token,sb_expires_at,created_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (token, uid, email, name, role, auth["access_token"],
                 auth.get("refresh_token", ""), sb_exp, stamp(created),
                 stamp(created + timedelta(days=SESSION_DAYS))),
            )
            con.commit()
            row = con.execute("SELECT * FROM sessions WHERE token=?",
                              (token,)).fetchone()
            con.close()
            sb("PATCH", "/rest/v1/vivaz_profiles?id=eq." + urllib.parse.quote(uid),
               {"last_login_at": stamp(created)},
               extra={"Prefer": "return=minimal"})
            cookie = ("%s=%s; Path=/; HttpOnly; Secure; SameSite=None; "
                      "Partitioned; Max-Age=%d"
                      % (COOKIE, token, SESSION_DAYS * 86400))
            return self._json(200, {"ok": True, "user": public_user(row),
                                    "token": token, "backend": "supabase"},
                              [("Set-Cookie", cookie)])

        if path == "/api/logout" and method == "POST":
            row = self._user()
            if row:
                if row["access_token"]:
                    sb("POST", "/auth/v1/logout", {}, apikey=ANON,
                       key=row["access_token"])
                con = sessions()
                con.execute("DELETE FROM sessions WHERE token=?", (row["token"],))
                con.commit()
                con.close()
            return self._json(200, {"ok": True}, [
                ("Set-Cookie", "%s=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
                 % COOKIE),
            ])

        # ---- estado: SEMPRE escopado ao dono, com RLS do usuário -----------
        if path == "/api/state" and method == "GET":
            row = self._auth()
            if row is None:
                return
            q = ("/rest/v1/vivaz_state?select=collection,payload"
                 "&owner_id=eq." + urllib.parse.quote(row["user_id"]))
            code, rows = user_sb(row, "GET", q)
            if code != 200 or not isinstance(rows, list):
                return self._json(502, {"error": "Supabase indisponível.",
                                        "detail": str(rows)[:200]})
            state = {r["collection"]: r["payload"] for r in rows}
            return self._json(200, {"state": state or None,
                                    "user": public_user(row),
                                    "owner_id": row["user_id"]})

        if path == "/api/state" and method == "PUT":
            row = self._auth()
            if row is None:
                return
            data = self._body()
            if not isinstance(data, dict) or not data:
                return self._json(400, {"error": "Estado inválido."})
            code, res = user_sb(row, "POST", "/rest/v1/rpc/vivaz_replace_state",
                                {"p_state": data, "p_user": row["user_id"]},
                                extra={"Prefer": "return=minimal"}, timeout=90)
            if code not in (200, 201, 204):
                return self._json(502, {"error": "Falha ao gravar no Supabase.",
                                        "detail": str(res)[:250]})
            return self._json(200, {"ok": True, "collections": len(data),
                                    "owner_id": row["user_id"]})

        if path == "/api/schema" and method == "GET":
            if self._auth() is None:
                return
            return self._json(200, {
                "backend": "supabase", "mode": "individual", "database": URL,
                "isolation": "RLS: owner_id = auth.uid() OR vivaz_is_admin()",
                "tables": {
                    "vivaz_profiles": "id uuid → auth.users | name | role | status | phone | RLS",
                    "vivaz_state": "PK (owner_id, collection) | payload jsonb | updated_at | updated_by | RLS",
                    "vivaz_audit": "user_id | owner_id | action | detail | created_at | RLS",
                },
                "functions": ["vivaz_is_admin", "vivaz_replace_state",
                              "vivaz_init_state", "vivaz_handle_new_user",
                              "vivaz_guard_profile"],
            })

        # ---- perfil / senha do próprio usuário ------------------------------
        if path == "/api/profile" and method == "PUT":
            row = self._auth()
            if row is None:
                return
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "JSON inválido."})
            patch = {}
            if "name" in data and str(data["name"]).strip():
                patch["name"] = str(data["name"]).strip()[:120]
            if "phone" in data:
                patch["phone"] = str(data["phone"]).strip()[:40]
            if not patch:
                return self._json(400, {"error": "Nada para atualizar."})
            code, res = user_sb(row, "PATCH",
                                "/rest/v1/vivaz_profiles?id=eq." +
                                urllib.parse.quote(row["user_id"]),
                                patch, extra={"Prefer": "return=minimal"})
            if code not in (200, 204):
                return self._json(502, {"error": "Falha ao atualizar perfil.",
                                        "detail": str(res)[:200]})
            if "name" in patch:
                con = sessions()
                con.execute("UPDATE sessions SET name=? WHERE token=?",
                            (patch["name"], row["token"]))
                con.commit()
                con.close()
            return self._json(200, {"ok": True, "profile": patch})

        if path == "/api/password" and method == "POST":
            row = self._auth()
            if row is None:
                return
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "JSON inválido."})
            atual = str(data.get("current", ""))
            nova = str(data.get("password", ""))
            if len(nova) < 8:
                return self._json(400, {"error": "A nova senha precisa de 8+ caracteres."})
            code, _ = sb("POST", "/auth/v1/token?grant_type=password",
                         {"email": row["email"], "password": atual},
                         key=ANON, apikey=ANON)
            if code != 200:
                return self._json(401, {"error": "Senha atual incorreta."})
            code, res = user_sb(row, "PUT", "/auth/v1/user", {"password": nova})
            if code != 200:
                return self._json(502, {"error": "Falha ao trocar a senha.",
                                        "detail": str(res)[:200]})
            return self._json(200, {"ok": True})

        # ---- gestão de equipe (somente admin) -------------------------------
        if path == "/api/admin/users" and method == "GET":
            if self._admin() is None:
                return
            code, res = sb("GET", "/auth/v1/admin/users?per_page=1000")
            users = res.get("users", []) if isinstance(res, dict) else []
            code2, profs = sb("GET", "/rest/v1/vivaz_profiles?select=id,name,role,status,phone,created_at,last_login_at")
            pmap = {p["id"]: p for p in profs} if isinstance(profs, list) else {}
            code3, rows = sb("GET", "/rest/v1/vivaz_state?select=owner_id,collection,payload")
            counts = {}
            if isinstance(rows, list):
                for r in rows:
                    c = counts.setdefault(r["owner_id"], {})
                    v = r["payload"]
                    if isinstance(v, list):
                        c[r["collection"]] = len(v)
            out = []
            for u in users:
                uid = u.get("id")
                p = pmap.get(uid, {})
                meta = u.get("user_metadata") or {}
                out.append({
                    "id": uid, "email": u.get("email"),
                    "name": p.get("name") or meta.get("name") or (u.get("email") or "").split("@")[0],
                    "role": p.get("role") or meta.get("role", "corretor"),
                    "status": p.get("status", "ativo"),
                    "phone": p.get("phone", ""),
                    "created_at": u.get("created_at"),
                    "last_login_at": p.get("last_login_at"),
                    "carteira": counts.get(uid, {}),
                    "colecoes": len(counts.get(uid, {})),
                })
            return self._json(200, {"users": out, "total": len(out)})

        if path == "/api/admin/state" and method == "GET":
            if self._admin() is None:
                return
            alvo = (query.get("user_id") or [""])[0]
            if not alvo:
                return self._json(400, {"error": "user_id obrigatório."})
            code, rows = sb("GET", "/rest/v1/vivaz_state?select=collection,payload"
                            "&owner_id=eq." + urllib.parse.quote(alvo))
            if code != 200 or not isinstance(rows, list):
                return self._json(502, {"error": "Falha ao consultar carteira."})
            resumo = {}
            for r in rows:
                v = r["payload"]
                resumo[r["collection"]] = len(v) if isinstance(v, list) else v
            return self._json(200, {"user_id": alvo, "resumo": resumo})

        if path == "/api/users" and method == "GET":
            if self._admin() is None:
                return
            return self._list_users()

        if path == "/api/users" and method == "POST":
            if self._admin() is None:
                return
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "JSON inválido."})
            email = str(data.get("email", "")).strip().lower()
            name = str(data.get("name", "")).strip()
            password = str(data.get("password", ""))
            role = str(data.get("role", "corretor"))
            if not email or "@" not in email or len(password) < 8:
                return self._json(400, {
                    "error": "Informe e-mail válido e senha com 8+ caracteres."})
            if role not in ("admin", "gerente", "corretor"):
                role = "corretor"
            code, res = sb("POST", "/auth/v1/admin/users", {
                "email": email, "password": password, "email_confirm": True,
                "user_metadata": {"name": name or email.split("@")[0],
                                  "role": role},
            })
            if code not in (200, 201):
                return self._json(409 if code in (409, 422) else 502,
                                  {"error": "Não foi possível criar o usuário.",
                                   "detail": str(res)[:200]})
            uid = (res.get("id") if isinstance(res, dict) else None) or \
                  ((res.get("user") or {}).get("id") if isinstance(res, dict) else None)
            # O trigger vivaz_handle_new_user cria o perfil E a carteira vazia.
            return self._json(201, {"ok": True, "email": email, "id": uid,
                                    "carteira": "vazia (13 coleções)"})

        m = re.fullmatch(r"/api/users/([0-9a-fA-F-]{36})/(reset-password)", path)
        if m and method == "POST":
            if self._admin() is None:
                return
            data = self._body()
            nova = str((data or {}).get("password", ""))
            if len(nova) < 8:
                return self._json(400, {"error": "Senha com 8+ caracteres."})
            code, res = sb("PUT", "/auth/v1/admin/users/" + m.group(1),
                           {"password": nova})
            if code != 200:
                return self._json(502, {"error": "Falha ao redefinir senha.",
                                        "detail": str(res)[:200]})
            return self._json(200, {"ok": True})

        m = re.fullmatch(r"/api/users/([0-9a-fA-F-]{36})", path)
        if m and method == "PATCH":
            admin = self._admin()
            if admin is None:
                return
            uid = m.group(1)
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "JSON inválido."})
            patch = {}
            if "name" in data and str(data["name"]).strip():
                patch["name"] = str(data["name"]).strip()[:120]
            if "role" in data and data["role"] in ("admin", "gerente", "corretor"):
                patch["role"] = data["role"]
            if "status" in data and data["status"] in ("ativo", "inativo"):
                patch["status"] = data["status"]
            if "phone" in data:
                patch["phone"] = str(data["phone"]).strip()[:40]
            if not patch:
                return self._json(400, {"error": "Nada para atualizar."})
            code, res = user_sb(admin, "PATCH",
                                "/rest/v1/vivaz_profiles?id=eq." +
                                urllib.parse.quote(uid), patch,
                                extra={"Prefer": "return=minimal"})
            if code not in (200, 204):
                return self._json(502, {"error": "Falha ao atualizar usuário.",
                                        "detail": str(res)[:200]})
            if uid == admin["user_id"] and "role" in patch:
                con = sessions()
                con.execute("UPDATE sessions SET role=? WHERE user_id=?",
                            (patch["role"], uid))
                con.commit()
                con.close()
            return self._json(200, {"ok": True, "id": uid, "patch": patch})

        return self._json(404, {"error": "Rota não encontrada."})

    def _list_users(self):
        code, res = sb("GET", "/auth/v1/admin/users?per_page=1000")
        users = res.get("users", []) if isinstance(res, dict) else []
        return self._json(200, {"users": [
            {"id": u.get("id"), "email": u.get("email"),
             "name": (u.get("user_metadata") or {}).get("name"),
             "role": (u.get("user_metadata") or {}).get("role", "corretor")}
            for u in users]})

    # ---------- dispatch ----------
    def do_GET(self):
        p = urlparse(self.path).path
        if p.startswith("/api/"):
            return self._api("GET")
        if p in ("/", "/index.html"):
            return self._serve_index()
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

    def do_PATCH(self):
        if urlparse(self.path).path.startswith("/api/"):
            return self._api("PATCH")
        return self._json(405, {"error": "Método não permitido."})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()


if __name__ == "__main__":
    sessions()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    print("VIVAZ · Supabase multi-tenant em http://0.0.0.0:%d | %s" % (PORT, URL))
    print("Storage: %s" % PHOTO_BASE)
    print("Login: %s / %s" % (ADMIN_EMAIL, ADMIN_PASSWORD))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
