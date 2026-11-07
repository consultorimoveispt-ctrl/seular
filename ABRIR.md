# Abrir o VIVAZ

## ✅ Forma mais simples: `ABRIR_APP.html` (não precisa de servidor)

Abra o arquivo **`ABRIR_APP.html`** no visualizador de arquivos do Arena
(ou baixe e dê duplo clique — funciona com `file://`).

É o app inteiro em **um único arquivo**: os 12 chunks JS foram unidos pelo
esbuild num **único script clássico** (zero `import()`, zero `type="module"`),
os 7 CSS viraram `<style>` inline, e as 51 fotos viraram *data URIs* resolvidas
por um interceptador de `<img>`. Não faz nenhuma requisição de rede, não depende
de porta e não morre quando o sandbox reinicia.

> **Por que não usa mais `data:text/javascript`:** o visualizador do Arena
> bloqueia módulos `data:` por CSP
> (`Failed to fetch dynamically imported module: data:text/javascript;base64,...`).
> A versão anterior usava *import map* + módulos em data URI e falhava só lá.
> Agora não há nenhum módulo: é um `<script>` comum.

Testado em `file://`, em iframe de origem opaca e com CSP estrito
(`default-src 'none'; script-src 'unsafe-inline'; img-src data:`):
login OK, **7/7 rotas**, **161 imagens**, **0 erros**, **0 falhas de rede**.

Login: `admin@vivaz.local` / `Vivaz@2026`

> Essa versão guarda os dados no `localStorage` do navegador (com fallback em
> memória). A versão com **Supabase de verdade + API** é a do servidor, abaixo.

Para regerar depois de qualquer alteração (requer `esbuild` em
`/home/user/.local/pw`): `python3 docs/build_offline.py`

---

## Versão com banco (Live Preview, porta 3000) ⭐

`./rodar.sh` — com `.env` presente ele escolhe **Supabase** automaticamente.
O painel aparece como **"VIVAZ · Supabase multi-tenant (porta 3000)"** na
aba/ícone **Preview** do Arena.

**Contas:** `admin@vivaz.local` / `Vivaz@2026` (admin, carteira de
demonstração) e `corretor@vivaz.local` / `Vivaz@2026` (corretor, carteira
vazia). As duas enxergam **apenas os próprios** imóveis, clientes, negócios e
financeiro.

- Use **sempre o painel Live Preview**: o endereço técnico do preview exige um
  token de tráfego que só o painel injeta; aberto cru numa aba nova dá `403`.
- `localhost:3000` no seu navegador aponta para a **sua** máquina, não para o sandbox.
- Se o sandbox reiniciar, o processo morre: rode `./rodar.sh` ou me peça para
  reiniciar. (O `ABRIR_APP.html` não tem esse problema.)
- Para voltar ao SQLite local: `VIVAZ_BACKEND=sqlite ./rodar.sh`.

### Backend Supabase multi-tenant (ativo desde 07/11)

| Onde | O quê |
|---|---|
| Login | **Supabase Auth** (com refresh automático do token) |
| Dados | `vivaz_state` com **`owner_id`** + `PK (owner_id, collection)` |
| Isolamento | **RLS** `owner_id = auth.uid()` — exceção só para admin |
| Sync | RPC `vivaz_replace_state` + `vivaz_audit` por dono |
| Novo usuário | trigger cria perfil **+ carteira vazia** (13 coleções) |
| Gestão | botão **"Equipe"** na barra superior (só admin): criar usuários, papéis, status, senhas, ver carteiras |
| Fotos | bucket público `vivaz-fotos` — **51/51 imagens** (160 `<img>` de lá) |
| Segurança | `service_role` só no servidor; estado é lido/gravado com o **JWT do usuário**, então o próprio banco barra acesso à carteira alheia |

O `server_supabase.py` é um proxy: o iframe sandboxed fala só com `/api/*`,
então não há problema de cookie de terceiros nem de CORS. Detalhes em
`README.md` e `docs/SUPABASE_PASSOS.md`.

Validação em iframe sandboxed: **2 usuários com carteiras distintas**,
**7/7 rotas** em cada uma, **161 imagens / 0 quebradas**, mutação persistida
apenas na carteira do dono, **0 erros JS** e **0 respostas ≥400**.
Teste direto no PostgREST: `SELECT`/`INSERT`/RPC na carteira de outro usuário
→ **403**. Capturas: `docs/preview-admin.png`,
`docs/preview-corretor-vazio.png`, `docs/preview-supabase.png`.

### O bug do login (corrigido em 07/11)

O Arena incorpora o preview num iframe com `sandbox="allow-scripts"` — **sem
`allow-forms`**. O botão era `type="submit"` dentro de um `<form>`; o Chrome
bloqueava o envio *antes* de qualquer JavaScript rodar
(`Blocked form submission to '' because the form's frame is sandboxed...`),
e por isso clicar não fazia nada, sem mensagem de erro.

Correções aplicadas:

| Item | Antes | Agora |
|---|---|---|
| Botão de login | `<form>` + `type="submit"` | `type="button"` + listener de `click` (e Enter nos campos) |
| Autenticação | só cookie `SameSite=Lax` | **token `Bearer`** (cookies de terceiros são bloqueados em iframe) |
| Requisições | sem CORS | `Access-Control-Allow-Origin` + preflight `OPTIONS` |
| `localStorage` | acesso direto | shim com fallback em memória (origem opaca) |
| Servidor fora do ar | silêncio | mensagem clara "Servidor indisponível..." |

Validação em iframe sandboxed: login OK, app `is-ready`, estado de 67920 bytes
vindo do banco, botão "Sair", **0 erros JS** e **0 respostas ≥400**.
Captura: `docs/preview-iframe.png`.

---

## Capturas em `docs/`

`preview-admin.png` · `preview-corretor-vazio.png` · `preview-supabase.png` ·
`preview-login.png` · `preview-app.png` · `preview-original.png` ·
`preview-iframe.png` · `preview-offline.png`
