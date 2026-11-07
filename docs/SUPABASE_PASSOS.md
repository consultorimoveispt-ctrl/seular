# VIVAZ → Supabase multi-tenant · **CONCLUÍDO** (07/11/2026)

Projeto: **`seular`** · ref `ezmvbknqtxupibbhyskp` · `us-east-1` · Postgres 17.
Provisionado pelo conector Supabase do Arena + scripts em Python padrão.

Decisões do usuário: isolamento **individual** (admin vê tudo), carteira
**vazia** para novos usuários, **painel de administração**, financeiro
**isolado junto com as demais coleções**.

## Migrations aplicadas

| # | Migration | O que fez |
|---|---|---|
| 1 | `vivaz_schema_inicial` | 3 tabelas, 10 views, RLS, trigger de perfil |
| 2 | `vivaz_multitenant_individual` | `owner_id`, `PK (owner_id, collection)`, RLS por dono, `vivaz_is_admin`, `vivaz_guard_profile`, RPC e `vivaz_init_state` |
| 3 | `vivaz_init_state_threads` | carteira vazia passou a incluir 1 conversa (o bundle exige `G.threads[0].id`) |

> Dois ajustes durante o caminho: o Postgres barrou `DELETE` sem `WHERE`
> (corrigido para `WHERE collection IS NOT NULL`) e a carteira vazia quebrava o
> boot do bundle por não ter `threads[0]` (corrigido com thread de boas-vindas).

## Estado atual do projeto

| Recurso | Resultado |
|---|---|
| `vivaz_profiles` | 2 perfis: `Marina Almeida` (admin) e `Rafael Corretor` (corretor) |
| `vivaz_state` | **26 linhas / 2 carteiras**: admin com 13 coleções de demonstração; corretor com 13 coleções **vazias** |
| `vivaz_audit` | `user:init` + `state:sync` com `user_id` e `owner_id` |
| RLS | `owner_id = auth.uid() OR vivaz_is_admin()` em SELECT/INSERT/UPDATE/DELETE |
| Auth | 2 usuários confirmados, senha validada pelo Supabase Auth |
| Storage | bucket público `vivaz-fotos`, **51/51 fotos** |

## Arquitetura

```
navegador (iframe sandbox="allow-scripts") ── /api/* + Bearer opaco ──> server_supabase.py
                                                                          │
              ┌───────────────────────────┬──────────────────────────────┴───────────┐
              ▼                           ▼                                          ▼
   /auth/v1/token (anon)      /rest/v1/vivaz_state  +  /rest/v1/rpc/...     /auth/v1/admin/users
   login + refresh             JWT DO USUÁRIO → RLS ativo                    service_role (admin)
```

- **`service_role` nunca sai do servidor.** O estado é lido/gravado com o
  access_token do usuário (renovado automaticamente) + `apikey: anon`.
- `boot.js` injeta `__VIVAZ_PHOTO_BASE__` → fotos do Storage, sem tocar nos bundles.
- `admin.js` só é importado quando `role === 'admin'`; adiciona o botão
  "Equipe" e o painel, sem alterar as 7 telas originais.
- `rodar.sh` escolhe Supabase com `.env`; `VIVAZ_BACKEND=sqlite` volta ao `server.py`.

## Arquivos

| Arquivo | Papel |
|---|---|
| `SCHEMA_SUPABASE.sql` | **schema definitivo** multi-tenant (consolidado) |
| `SEED_SUPABASE.sql` | 13 coleções de demonstração **só para o admin**, via `owner_id` |
| `aplicar_supabase.py` | idempotente: admin → perfil → seed → bucket → 51 fotos |
| `upload_fotos_supabase.py` | upload isolado das fotos (`--apply`) |
| `SUPABASE.env.example` | modelo de credenciais |
| `.env` (raiz, modo 600) | credenciais reais — não versionar, não servir |

Reprovisionar: `python3 docs/aplicar_supabase.py`

## Credenciais

| E-mail | Senha | Papel | Carteira |
|---|---|---|---|
| `admin@vivaz.local` | `Vivaz@2026` | admin | demonstração (16 imóveis, 20 clientes, 45 negócios) |
| `corretor@vivaz.local` | `Vivaz@2026` | corretor | vazia (conta de teste) |

## Validação

```
GET  /api/health          → 200 {mode: individual, carteiras: 2, vivaz_state: 26}
POST /api/login errada    → 401 · conta inativa → 403
GET  /api/state (admin)   → 13 coleções, 16 imóveis, owner_id = admin
GET  /api/state (corretor)→ 13 coleções,  0 imóveis, owner_id = corretor
PUT  /api/state           → 200, gravou só na carteira do dono + vivaz_audit
corretor → /api/admin/* , POST /api/users  → 403
admin    → /api/admin/users → 2 usuários com contadores por carteira
```

**RLS direto no PostgREST (sem o proxy), com o JWT do corretor:**

| Operação | Resultado |
|---|---|
| `SELECT * FROM vivaz_state` | 13 linhas, todas do próprio `owner_id` |
| `SELECT ... WHERE owner_id = <admin>` | **0 linhas** |
| `INSERT` na carteira do admin | **403** `row-level security policy` |
| `vivaz_replace_state(..., p_user=<admin>)` | **403** `Acesso negado` |
| Mesmo SELECT com JWT do admin | **26 linhas / 2 donos** |

**Chromium headless em iframe `sandbox="allow-scripts"`**:

- Admin: login, painel com 2 usuários/KPIs, "Ver carteira", 0 erros JS, 0 HTTP ≥ 400.
- Corretor: login, `is-ready`, carteira vazia, **7/7 rotas**, sem botão Equipe,
  0 erros JS, 0 HTTP ≥ 400.
- Papel, status (ativar/desativar), perfil, troca/redefinição de senha testados.

Capturas: `preview-admin.png`, `preview-corretor-vazio.png`,
`preview-supabase.png`.
