# VIVAZ — CRM imobiliário profissional, multi-tenant, com Supabase

Cópia **idêntica** de `https://vivaz.afcode.com.br/#/overview`, agora com
**login, carteira individual por usuário, gestão de equipe e banco no Supabase**,
rodando na porta **3000**.

> O site público não tem backend: a análise com REA confirmou que ele guarda
> tudo em `localStorage`. As peças de servidor foram **acrescentadas** — os 19
> bundles JS/CSS, as 51 fotos e o HTML que desenham a tela continuam sendo os
> arquivos originais, sem nenhuma reescrita.

---

## O que mudou nesta versão

**Cada usuário tem seus próprios imóveis, clientes, negócios, leads, tarefas,
documentos, conversas e comissões/financeiro.** O isolamento não é só da
aplicação: é garantido por **RLS no Postgres** (`owner_id = auth.uid()`), com
exceção apenas para administradores.

| Antes | Agora |
|---|---|
| `vivaz_state` global: 1 linha por coleção para todo mundo | `PK (owner_id, collection)` — uma carteira por usuário |
| Chamadas PostgREST com `service_role` | Estado lido/gravado com o **access_token do usuário** → RLS ativo |
| Um único usuário admin | Usuários com papéis `admin` / `gerente` / `corretor`, status ativo/inativo |
| Gestão só por API | **Painel "Equipe e carteiras"** dentro do app |
| Novo usuário herdava os dados do admin | Novo usuário nasce com **carteira vazia** (via trigger) |
| Sem auditoria por dono | `vivaz_audit` registra `user_id` + `owner_id` em cada sync |

---

## Três formas de abrir

| # | Forma | Backend | Como |
|---|---|---|---|
| 1 | **`ABRIR_APP.html`** | 100% offline (`localStorage`) | Abra no visualizador do Arena ou com `file://`. Sem servidor, rede ou porta. |
| 2 | **Live Preview · porta 3000** ⭐ | **Supabase multi-tenant** | Painel "Live Preview" do Arena → **"VIVAZ · Supabase multi-tenant (porta 3000)"**. |
| 3 | SQLite local | `server.py` | `VIVAZ_BACKEND=sqlite bash rodar.sh` |

### Contas

| E-mail | Senha | Papel | Carteira |
|---|---|---|---|
| `admin@vivaz.local` | `Vivaz@2026` | admin | demonstração: 16 imóveis, 20 clientes, 45 negócios |
| `corretor@vivaz.local` | `Vivaz@2026` | corretor | **vazia** (conta de teste do isolamento) |

> Use sempre o painel **Live Preview**. O endereço técnico do preview exige um
> token de tráfego que só o painel injeta; abrir direto numa aba nova dá `403`.
> `localhost` no seu navegador aponta para a sua máquina, não para o sandbox.

Se o sandbox reiniciar, o processo morre: rode `./rodar.sh` ou peça para eu
reiniciar. O `ABRIR_APP.html` não tem esse problema.

---

## Banco (projeto `seular` · `ezmvbknqtxupibbhyskp` · `us-east-1`)

| Objeto | Função |
|---|---|
| `vivaz_profiles` | `id → auth.users`, `name`, `role`, `status`, `phone`, `avatar_url`, timestamps |
| `vivaz_state` | `PK (owner_id, collection)`, `payload jsonb`, `updated_at`, `updated_by` |
| `vivaz_audit` | `user_id` (quem agiu) + `owner_id` (de quem é a carteira) + ação |
| 10 views | `vivaz_members` … `vivaz_notices`, todas com `security_invoker` e `owner_id` |
| `vivaz_is_admin()` | helper `security definer` usado pelas policies |
| `vivaz_handle_new_user()` | trigger: cria perfil **e carteira vazia** para todo novo usuário |
| `vivaz_init_state()` | 13 coleções vazias + 1 conversa de boas-vindas (o bundle exige `threads[0]`) |
| `vivaz_replace_state()` | RPC: substitui atomicamente **só** a carteira do dono + auditoria |
| `vivaz_guard_profile()` | impede que um não-admin altere o próprio `role`/`status` |

**RLS**
- `vivaz_state`: `SELECT/INSERT/UPDATE/DELETE` → `owner_id = auth.uid() OR vivaz_is_admin()`
- `vivaz_profiles`: próprio perfil ou admin
- `vivaz_audit`: próprias linhas ou admin

Arquivos: `docs/SCHEMA_SUPABASE.sql` (schema definitivo), `docs/SEED_SUPABASE.sql`,
`docs/aplicar_supabase.py` (idempotente), `docs/upload_fotos_supabase.py`.

---

## Arquitetura

```
navegador (iframe sandbox="allow-scripts")
   │  /api/* + Bearer opaco
   ▼
server_supabase.py  ──── service_role (só aqui) ──> Auth Admin API, /api/admin/*
   │  access_token DO USUÁRIO + apikey anon
   ▼
PostgREST → RLS (owner_id = auth.uid()) → vivaz_state / RPC
   │
fotos: boot.js reescreve <img src> ──> Storage público vivaz-fotos
```

- **`service_role` nunca sai do servidor.** As operações de estado usam o JWT
  do próprio usuário (com **refresh automático**), então o banco barra qualquer
  tentativa de ler outra carteira mesmo que alguém burlasse o proxy.
- `boot.js` mantém o contrato original: exige login, busca `/api/state`, injeta
  no `localStorage`, importa o bundle. Toda alteração da UI → `PUT /api/state`
  → `vivaz_replace_state` no Postgres.
- Sessões de 30 dias ficam num SQLite minúsculo (`data/supabase_sessions.db`),
  só com tokens, para o login sobreviver a restart.
- Credenciais em `.env` (modo `600`, `GET /.env` → 404).

---

## Painel de administração

Botão **"Equipe"** na barra superior (só aparece para `admin`). É uma tela nova
que **não altera nenhuma das 7 telas originais**:

- KPIs: usuários, ativos, imóveis, clientes e negócios de todas as carteiras
- Tabela de usuários com **papel** (select), **status** (ativar/desativar) e
  tamanho da carteira de cada um
- **Criar usuário** (nome, e-mail, senha, papel) → carteira vazia automática
- **Ver carteira** de qualquer usuário (resumo por coleção)
- **Redefinir senha** de um usuário
- **Minha conta**: nome, telefone e troca da própria senha (valida a atual)

Contas inativas são barradas no login (`403 Conta desativada`).

---

## API

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/health` | Saúde, `mode: individual`, nº de carteiras |
| GET | `/api/session` | `{authenticated, user}` (sempre 200) |
| GET | `/api/me` | Usuário + perfil completo |
| POST | `/api/login` | Valida no **Supabase Auth**; devolve token Bearer |
| POST | `/api/logout` | Encerra sessão local + Auth |
| GET | `/api/state` | **Só** as 13 coleções do dono (RLS) |
| PUT | `/api/state` | `vivaz_replace_state` + auditoria |
| GET | `/api/schema` | Tabelas, funções e regra de isolamento |
| GET | `/api/admin/users` | Lista usuários + tamanho de cada carteira **(admin)** |
| GET | `/api/admin/state?user_id=` | Resumo da carteira de outro usuário **(admin)** |
| GET/POST | `/api/users` | Lista / cria usuário com carteira vazia **(admin)** |
| PATCH | `/api/users/:id` | Papel, status, nome, telefone **(admin)** |
| POST | `/api/users/:id/reset-password` | Nova senha **(admin)** |
| PUT | `/api/profile` | Nome/telefone do próprio usuário |
| POST | `/api/password` | Troca de senha (exige a atual) |

CORS + preflight `OPTIONS` para o iframe. Senha nunca é conferida no servidor
local: quem valida é o Supabase Auth.

---

## Validação (Chromium headless, iframe `sandbox="allow-scripts"`)

**Isolamento no banco (teste direto no PostgREST, sem o proxy):**

| Teste com o JWT do corretor | Resultado |
|---|---|
| `SELECT * FROM vivaz_state` | 13 linhas, **todas com o próprio `owner_id`** |
| `SELECT ... WHERE owner_id = <admin>` | **0 linhas** |
| `INSERT` na carteira do admin | **403** `row-level security policy` |
| RPC `vivaz_replace_state(..., p_user=<admin>)` | **403** `Acesso negado: carteira de outro usuário` |
| Mesmo SELECT com JWT do admin | **26 linhas / 2 donos** |

**Aplicação:**

- Admin: login OK, painel abre com 2 usuários e KPIs, "Ver carteira" funciona,
  **0 erros JS / 0 HTTP ≥ 400**.
- Corretor: login OK, `is-ready`, **carteira vazia** (0 imóveis, 0 clientes,
  0 negócios), **7/7 rotas renderizam**, **botão Equipe ausente**, **0 erros**.
- Mutação do corretor gravou só na carteira dele; admin continuou com 16 imóveis.
- Papel/status/perfil/senha/redefinição testados; conta inativa barrada no login.
- Estado vazio com mensagem própria no carrossel (o app original não previa zero imóveis).
- `ABRIR_APP.html`: `file://`, iframe opaco e CSP estrito → 7/7 rotas,
  161 imagens, 0 erros; zero `type="module"`, zero `import()`, zero `data:` JS.
- Capturas: `docs/preview-admin.png`, `docs/preview-corretor-vazio.png`,
  `docs/preview-supabase.png`, `docs/preview-iframe.png`, `docs/preview-offline.png`.

---

## Rodar

```bash
cd /home/user/vivaz
./rodar.sh                              # escolhe Supabase automaticamente (.env)
VIVAZ_BACKEND=sqlite ./rodar.sh         # força o backend SQLite original
python3 docs/aplicar_supabase.py        # reprovisiona (idempotente)
python3 docs/build_offline.py           # regera ABRIR_APP.html (requer esbuild)
```

Só Python 3 padrão. Sem `npm install`, sem build de frontend.

---

## Estrutura

```
vivaz/
├─ ABRIR_APP.html              ★ app inteiro em 1 arquivo, sem servidor/rede
├─ ABRIR.md / README.md
├─ .env                        credenciais Supabase (modo 600, não versionar)
├─ server_supabase.py          ★ proxy multi-tenant + gestão de equipe
├─ server.py                   backend SQLite (fallback, intacto)
├─ rodar.sh
├─ public/
│  ├─ index.html               HTML do site (2 ajustes mínimos)
│  ├─ boot.js                  login + sync + fotos + estado vazio
│  ├─ admin.js                 ★ painel "Equipe e carteiras" (só admin)
│  ├─ assets/                  19 bundles JS/CSS originais
│  └─ vivaz/photos/...         51 fotos (fallback local)
├─ data/
│  ├─ seed.json                estado de demonstração do admin
│  ├─ vivaz.db                 SQLite (backend 3)
│  └─ supabase_sessions.db     só tokens de sessão
└─ docs/
   ├─ SUPABASE_PASSOS.md       provisionamento + resultados
   ├─ SCHEMA_SUPABASE.sql      ★ schema multi-tenant definitivo
   ├─ SEED_SUPABASE.sql        seed só do admin (owner_id)
   ├─ aplicar_supabase.py      seed + usuário + bucket + fotos
   ├─ upload_fotos_supabase.py upload isolado
   ├─ SUPABASE.env.example     modelo de credenciais
   ├─ build_offline.py         gera ABRIR_APP.html
   ├─ index-original.html      HTML byte a byte do site
   ├─ RELATORIO_REA.md         análise REA do frontend público
   └─ preview-*.png
```

## Diferenças em relação ao HTML do site

1. Removida a linha do script anti-devtools do CDN.
2. `<script type="module" src="/assets/index-hGLYjae8.js">` virou `/boot.js`,
   que importa o bundle após o login.
3. `boot.js` adiciona o botão "Sair", reescreve as URLs das fotos, aplica o
   estado vazio e (para admin) carrega `admin.js`.

**Nenhum bundle, CSS ou imagem original foi modificado.**
