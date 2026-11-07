#!/usr/bin/env python3
"""Provisiona o projeto Supabase com o VIVAZ multi-tenant (stdlib).

Ordem importa: o trigger vivaz_handle_new_user cria perfil + carteira vazia
para TODO usuário novo. Por isso criamos o admin primeiro e só depois
sobrescrevemos as 13 coleções dele com os dados de demonstração.

  python3 docs/aplicar_supabase.py       # idempotente, pode rodar de novo
"""
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = "/home/user/vivaz"
PDIR = os.path.join(ROOT, "public/vivaz/photos/175-vivaz")
PREFIX = "vivaz/photos/175-vivaz/"

env = {}
for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        env[k] = v

URL = env["SUPABASE_URL"].rstrip("/")
KEY = env["SUPABASE_SERVICE_ROLE_KEY"]
BUCKET = env.get("SUPABASE_BUCKET", "vivaz-fotos")
EMAIL = env.get("VIVAZ_ADMIN_EMAIL", "admin@vivaz.local")
PASSWORD = env.get("VIVAZ_ADMIN_PASSWORD", "Vivaz@2026")


def call(method, path, body=None, ctype="application/json", extra=None):
    headers = {"apikey": KEY, "Authorization": "Bearer " + KEY,
               "Content-Type": ctype}
    headers.update(extra or {})
    data = (json.dumps(body).encode() if body is not None
            and ctype == "application/json" else body)
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw and
                              r.headers.get("content-type", "").startswith("application/json")
                              else raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode("utf-8", "replace")


def step(n, title):
    print("\n[%d] %s" % (n, title), flush=True)


# -------------------------------------------------- 1) usuário admin
step(1, "Usuário admin no Supabase Auth")
code, res = call("POST", "/auth/v1/admin/users", body={
    "email": EMAIL, "password": PASSWORD, "email_confirm": True,
    "user_metadata": {"name": "Marina Almeida", "role": "admin"},
})
print("   POST /auth/v1/admin/users ->", code)
if code in (200, 201):
    uid = res.get("id") if isinstance(res, dict) else res["user"]["id"]
elif code in (409, 422):
    c2, users = call("GET", "/auth/v1/admin/users?per_page=1000")
    listed = users.get("users", users) if isinstance(users, dict) else users
    uid = next((u["id"] for u in listed if u.get("email") == EMAIL), None)
else:
    sys.exit("   falha ao criar usuário: " + str(res)[:300])
if not uid:
    sys.exit("   usuário não encontrado")
print("   uid:", uid)

# -------------------------------------------------- 2) perfil
step(2, "Perfil admin")
code, res = call("PATCH", "/rest/v1/vivaz_profiles?id=eq." + uid,
                 body={"role": "admin", "name": "Marina Almeida",
                       "status": "ativo"},
                 extra={"Prefer": "return=representation"})
print("   perfil ->", code, res if isinstance(res, list) else str(res)[:120])

# -------------------------------------------------- 3) seed do ADMIN apenas
step(3, "Dados de demonstração SÓ na carteira do admin")
seed = json.load(open(os.path.join(ROOT, "data/seed.json"), encoding="utf-8"))
rows = [{"owner_id": uid, "collection": k, "payload": v}
        for k, v in seed.items()]
code, res = call("POST", "/rest/v1/vivaz_state", body=rows,
                 extra={"Prefer": "resolution=merge-duplicates,return=minimal"})
print("   upsert %d coleções -> %s" % (len(rows), code),
      "" if code in (200, 201, 204) else str(res)[:200])
if code not in (200, 201, 204):
    sys.exit("   falha no seed (o schema multi-tenant foi aplicado?)")
code, donos = call("GET", "/rest/v1/vivaz_state?select=owner_id")
print("   donos com carteira:", len({r["owner_id"] for r in donos})
      if isinstance(donos, list) else donos)

# -------------------------------------------------- 4) storage
step(4, "Bucket público e fotos")
code, res = call("POST", "/storage/v1/bucket", body={
    "id": BUCKET, "name": BUCKET, "public": True,
    "file_size_limit": 5242880,
    "allowed_mime_types": ["image/jpeg", "image/png", "image/webp"],
})
print("   criar bucket ->", code,
      "(já existe)" if code in (400, 409) else str(res)[:120])
if code in (400, 409):
    # Supabase responde 400 ou 409 quando o bucket já existe; garantimos
    # que ele continue público de qualquer forma.
    c2, r2 = call("PUT", "/storage/v1/bucket/" + BUCKET,
                  body={"public": True})
    print("   tornar público ->", c2)

files = sorted(f for f in os.listdir(PDIR)
               if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
ok = fail = 0
for f in files:
    with open(os.path.join(PDIR, f), "rb") as fh:
        raw = fh.read()
    ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
    obj = urllib.parse.quote(PREFIX + f, safe="/")
    code, res = call("POST", "/storage/v1/object/%s/%s" % (BUCKET, obj),
                     body=raw, ctype=ctype, extra={"x-upsert": "true"})
    if code in (200, 201, 204):
        ok += 1
    else:
        fail += 1
        print("   FALHA", f, code, str(res)[:120])
print("   fotos enviadas: %d/%d (falhas %d)" % (ok, len(files), fail))

PUBLIC = URL + "/storage/v1/object/public/" + BUCKET + "/" + PREFIX
print("\n[5] URL pública das fotos:\n   ", PUBLIC)
print("\nRESUMO: admin =", EMAIL, "| carteiras isoladas por owner_id |"
      " fotos =", ok)
