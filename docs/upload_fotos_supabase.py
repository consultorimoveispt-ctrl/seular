#!/usr/bin/env python3
"""Envia as 51 fotos do app para o Supabase Storage (stdlib, sem dependências).

Caminho dentro do bucket: vivaz/photos/175-vivaz/<arquivo>
Assim a URL pública fica:
  https://<proj>.supabase.co/storage/v1/object/public/<bucket>/vivaz/photos/175-vivaz/<arquivo>
e basta trocar a constante de prefixo de fotos no bundle.

Uso:
  python3 docs/upload_fotos_supabase.py            # mostra o plano (dry-run)
  python3 docs/upload_fotos_supabase.py --apply    # cria bucket e envia
"""
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

ROOT = "/home/user/vivaz"
PDIR = os.path.join(ROOT, "public/vivaz/photos/175-vivaz")
PREFIX = "vivaz/photos/175-vivaz/"

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = os.environ.get("SUPABASE_BUCKET", "vivaz-fotos")
APPLY = "--apply" in sys.argv


def call(method, path, body=None, content_type="application/json", extra=None):
    headers = {
        "apikey": KEY,
        "Authorization": "Bearer " + KEY,
        "Content-Type": content_type,
    }
    headers.update(extra or {})
    data = None
    if body is not None:
        data = (json.dumps(body).encode() if content_type == "application/json"
                else body)
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


files = sorted(f for f in os.listdir(PDIR)
               if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
print("bucket:", BUCKET)
print("arquivos:", len(files))
print("URL base:", URL + "/storage/v1/object/public/" + BUCKET + "/" + PREFIX)

if not URL or not KEY:
    print("\nDefina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY (veja .env.example).")
    sys.exit(1)

if not APPLY:
    print("\nDRY-RUN: nada foi enviado. Use --apply para executar.")
    for f in files[:5]:
        print("  ->", PREFIX + f)
    print("  ...")
    sys.exit(0)

code, body = call("POST", "/storage/v1/bucket", {
    "id": BUCKET, "name": BUCKET, "public": True
})
print("criar bucket:", code, "(409 = já existe)" if code == 409 else body[:120])

ok = fail = 0
for f in files:
    path = os.path.join(PDIR, f)
    with open(path, "rb") as fh:
        raw = fh.read()
    ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
    code, body = call(
        "POST",
        "/storage/v1/object/%s/%s%s" % (BUCKET, PREFIX, f),
        body=raw, content_type=ctype, extra={"x-upsert": "true"},
    )
    if code in (200, 201, 204):
        ok += 1
    else:
        fail += 1
        print("  FALHA", f, code, body[:120])
    print("  %3d/%3d %s %s" % (ok + fail, len(files), f, code))

print("\nenviados:", ok, "| falhas:", fail)
print("URL pública de exemplo:",
      URL + "/storage/v1/object/public/" + BUCKET + "/" + PREFIX + files[0])
