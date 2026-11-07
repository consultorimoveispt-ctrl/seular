# Publicar no GitHub

Repositório: **https://github.com/consultorimoveispt-ctrl/seular.git**
(`main`, público, criado em 07/11/2026).

> ✅ **PUBLICADO** em 07/11/2026 · commit inicial `53c7201` · **106 arquivos** ·
> CI `CI / validar` = **success**. `.env` e bancos locais não estão no remoto.
> Para novos commits: `git add -A && git commit -m "..." && ./publicar.sh`
> (com `GITHUB_TOKEN`) ou `./publicar-ssh.sh` (com a deploy key).

## O que vai para o repositório

| Incluído | Excluído (`.gitignore`) |
|---|---|
| `server.py`, `server_supabase.py`, `rodar.sh` | **`.env`** (chave `service_role` real) |
| `public/` (HTML, `boot.js`, `admin.js`, 19 bundles, 51 fotos) | `data/*.db` (senhas/tokens de sessão) |
| `ABRIR_APP.html` (app offline em 1 arquivo) | `__pycache__`, `*.log`, `docs/debug-*.png` |
| `data/seed.json`, `docs/*.sql`, `docs/*.py`, `docs/*.md` | `.env.*` (exceto `.env.example`) |
| `.github/workflows/ci.yml`, capturas `preview-*.png` | `node_modules/`, `.local/` |

> Antes do commit foi feita uma varredura pelo prefixo de JWT do Supabase:
> **nenhuma chave em arquivo versionado**. O `.env` real tem modo `600` e
> `GET /.env` no servidor retorna `404`.

## Fazer o push

O sandbox não tem credencial GitHub e o conector GitHub não é oferecido neste
Arena. Escolha uma das três formas:

### 1) Personal Access Token (mais rápido)

Crie/edite um **fine-grained token** em GitHub → Settings → Developer
settings → Personal access tokens → Fine-grained tokens:

- **Repository access**: *Only select repositories* → `seular`
- **Repository permissions**:
  - `Metadata: read` (automático, obrigatório)
  - **`Contents: Read and write`** ← sem isso o push dá `403`
  - **`Workflows: Read and write`** ← o commit inclui
    `.github/workflows/ci.yml`; o GitHub exige essa permissão extra para
    pushes que tocam arquivos de workflow
- Expiração curta

> Alternativa mais simples: um **classic PAT** com o escopo `repo` (ele já
> cobre Contents + Workflows).

Depois:

```bash
cd /home/user/vivaz
GITHUB_TOKEN=seu_token ./publicar.sh
```

O token é enviado só como header HTTP naquele push — **não é gravado** no
`remote`, em arquivo ou no histórico. Depois de publicar, revogue o token.

### 2) Chave de deploy SSH (recomendado quando o PAT é read-only)

A chave já foi gerada no sandbox. Cole o conteúdo abaixo em GitHub → `seular` →
**Settings → Deploy keys → Add deploy key**, marcando **Allow write access**:

```bash
cat ~/.ssh/vivaz_deploy.pub
```

Depois é só avisar e eu rodo (ou rode você mesmo):

```bash
cd /home/user/vivaz
./publicar-ssh.sh
```

> A chave privada fica apenas no sandbox (`~/.ssh/vivaz_deploy`, modo 600) e
> **não** está no repositório. A porta SSH do GitHub está aberta no sandbox.

### 2b) Sem credencial nenhuma: pacote pronto

Também deixei `/home/user/seular.zip` (todos os 105 arquivos versionados, sem
segredos) e `/home/user/seular.bundle` (histórico git completo). Você pode:

- extrair o ZIP e usar **Add file → Upload files** na interface do GitHub; ou
- `git clone /home/user/seular.bundle seular && cd seular && git remote set-url origin https://github.com/consultorimoveispt-ctrl/seular.git && git push origin main`

### 3) Você mesmo, na sua máquina

```bash
git clone https://github.com/consultorimoveispt-ctrl/seular.git
# copie o conteúdo de /home/user/vivaz para a pasta clonada
git add -A && git commit -m "VIVAZ: app multi-tenant com Supabase"
git push origin main
```

## Solução de problemas

| Sintoma | Causa / ação |
|---|---|
| `could not read Username for 'https://github.com'` | nenhuma credencial foi enviada (token não definido) |
| `403 Permission to ... denied to <usuario>` | token sem `Contents: write`. Confirme em Developer settings → Fine-grained tokens → Permissions |
| `403 Resource not accessible by personal access token` (API) | idem. O header `x-accepted-github-permissions: contents=write` confirma a permissão faltante |
| `refusing to allow ... to create or update workflow` | falta `Workflows: write` no token fine-grained |
| `422` ao criar ref via API | payload inválido (falta `sha`), não é problema de permissão |

Diagnóstico rápido sem expor o token:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/user                       # 200 = token válido
curl -s -o /dev/null -D - -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/consultorimoveispt-ctrl/seular/git/blobs \
  -d '{"content":"probe","encoding":"utf-8"}' \
  | grep -iE 'HTTP/|x-accepted-github-permissions'  # 403 = falta contents:write
```

## CI

`.github/workflows/ci.yml` roda em todo push/PR para `main`:

- `python -m py_compile` em `server.py`, `server_supabase.py` e `docs/*.py`
- `node --check` em `public/boot.js` e `public/admin.js`
- verifica que `ABRIR_APP.html` não tem `type="module"`, import map,
  módulos `data:` nem recursos externos
- falha se alguma chave JWT do Supabase aparecer em arquivo versionado
  ou se `.env` tiver sido commitado

## Para rodar em produção depois do push

1. `cp .env.example .env` e preencha `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY` (o `.env` nunca sobe).
2. No Supabase, aplique `docs/SCHEMA_SUPABASE.sql` no SQL Editor.
3. `python3 docs/aplicar_supabase.py` — cria admin, seed só na carteira dele,
   bucket e 51 fotos.
4. `./rodar.sh` (porta 3000) ou `VIVAZ_BACKEND=sqlite ./rodar.sh` sem Supabase.
5. `ABRIR_APP.html` funciona sem nada disso, direto no navegador.

Detalhes de arquitetura e provisionamento: `README.md` e
`docs/SUPABASE_PASSOS.md`.
