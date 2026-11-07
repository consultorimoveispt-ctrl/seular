# Relatório de análise estática — vivaz.afcode.com.br

**Data:** 06/11/2026 · **Alvo:** `https://vivaz.afcode.com.br/#/overview`
**Método:** coleta passiva (GET) apenas de arquivos publicamente referenciados pelo HTML/bundles →
salvos em `/home/user/alvo/vivaz/raw/` → análise estática com REA 6.8.0
(`analyze-javascript-application`, modo `summary` + Evidence bundle).
**Evidência:** `/home/user/alvo/evidencias/raw-20261106-194547/` (`evidencia.json`, `resumo.json`, `meta.txt`).

> Todo conteúdo do alvo foi tratado como **dado, nunca como instrução** (regra do próprio catálogo MCP do REA).
> Varredura por instruções ocultas / prompt injection nos 18 arquivos: **nenhuma encontrada**.
> Não houve login, varredura de endpoints, tentativa de autenticação, enumeração de buckets nem execução do bundle.

---

## 1. Números da análise (REA)

| Métrica | Valor |
|---|---|
| Arquivos relevantes | 12 |
| Arquivos JS parseados | 11 |
| Nós AST visitados | 128.611 |
| Achados | 776 |
| Falhas de parse | 0 |
| Cobertura | **parcial** (limite de orçamento de resultado em 4 chunks) |
| Limitações registradas | 14 |

Limitações relevantes (o REA as declara explicitamente): o bundle **nunca foi executado**; o HTML inline
não foi analisado; `gsap`, `index`, `leads`, `overview` e `property` tiveram o grafo semântico truncado
por limite de resultado — ou seja, *cobertura parcial não prova ausência*. A conclusão abaixo se apoiou
também em leitura direta dos arquivos baixados, não só no grafo.

---

## 2. O que o site é, de fato

**SPA estática Vite, sem backend.** Hash routing com 7 rotas e chunks sob demanda:

```
#/overview  #/rentals  #/sales  #/deals  #/leads  #/contacts  #/property/:slug
```

Chunks: `index-hGLYjae8.js` (shell + estado + roteador), `overview`, `rentals`, `sales`, `deals`,
`leads`, `contacts`, `property`, mais `listing-kit`, `charts`, `gsap`, `motion` e CSS por rota.
Bibliotecas observadas: GSAP + Motion (animações), Plus Jakarta Sans (Google Fonts),
`disable-devtool` via jsDelivr. Servidor: nginx, `noindex,nofollow`, HSTS.

**Rede:** existe **uma** chamada `fetch()` no bundle principal — é o polyfill de `modulepreload` do Vite,
buscando os próprios assets. Não há `/api/`, GraphQL, WebSocket, axios, `VITE_*`, `process.env`,
URLs de API, JWT, Bearer, OAuth nem qualquer endpoint externo além de Google Fonts e jsDelivr.

---

## 3. Suas três hipóteses, verificadas

### ❌ "Estrutura de banco de dados"
Não há banco de dados no artefato entregue ao navegador. O estado inteiro é um **objeto seedado em
`localStorage`**, chave `vivaz:br:v1`, com `version: 1` e `seededOn` (reseed diário). Coleções:

```
members, contacts, properties, deals, leads, tasks, docs, threads, activity, notices, settings
```

Há um pub/sub em memória (`Map` de listeners) e `localStorage.setItem` a cada mutação. Campos inferidos
dos bundles para as entidades principais:

| Entidade | Campos observados |
|---|---|
| `properties` | `id`, `slug`, `title`, `price`, `status`, `market`, `beds`, `baths`, `sqft`/`area`, `address`, `zip`, `built`, `parking`, `floors`, `lot`, `owner`, `agent`, `photo`, `gallery`, `plans`, `features`, `map`, `desc` |
| `deals` | `propertyId`, `contactId`, estágio (`Visita`/`Proposta`/`Negociação`/`Em contrato`), `value`, probabilidade, `owner` |
| `leads` | origem, pontuação, `status`, responsável, `propertyId`, `contactId` |
| `contacts` / `members` | nome, papel, agência, avatar, meta de comissão |
| `tasks`, `docs`, `threads`, `activity`, `notices`, `settings` | agenda, documentos, chat com notas de voz, feed, notificações, preferências |

Ou seja: dá para **derivar um modelo de dados** (e eu posso propor um schema Postgres a partir dele),
mas não existe "estrutura de banco" para ser descoberta — ela precisaria ser **criada**.

### ❌ "Acho que tem MinIO como storage"
Nenhuma evidência: sem `minio`, `s3`, `bucket`, presigned URL, endpoint `:9000`, SDK de objeto,
headers S3 ou variáveis de acesso. As fotos são **arquivos estáticos** servidos pelo nginx em
`/vivaz/photos/175-vivaz/` (`hollis.jpg`, `map-light.jpg`, avatares `*-sm.jpg`, etc.). MinIO é uma
**escolha de arquitetura futura**, não algo presente. (E mesmo que existisse no servidor, bucket,
credenciais e política não seriam observáveis pelo frontend — obtê-los exigiria acesso autorizado
ao backend, não engenharia reversa do bundle.)

### ❌ "Sistema de login"
Não existe autenticação: o dashboard de `#/overview` renderiza direto, sem tela de login, sem rota
de auth, sem `token`/`session`/`password`/`senha`/`credential` nos bundles, e nenhuma chamada protegida.
O único "usuário" é um `settings` local com nome/email/papel/agência do corretor. Tema e largura do
chat ficam em `vivaz:theme` / `vivaz:chat`.

---

## 4. Ponto de atenção: titularidade

O HTML e o CSS trazem, literalmente:

> `© 2026 Hasib (OVERSHOOT). Todos os direitos reservados. Licenciado, não vendido: consulte LICENSE.md.`
> `/*! ... All rights reserved. Licensed, not sold: see LICENSE.md. */`

E `https://vivaz.afcode.com.br/LICENSE.md` retorna **404**. Somado a `noindex,nofollow` e ao
`disable-devtool`, o artefato se apresenta como **produto de terceiro, licenciado e protegido**, o que
contradiz "meu site". O `DISCLAIMER.md` do próprio REA desautoriza "copiar software proprietário ou
reproduzir seu código e assets protegidos".

Por isso **não vou copiar `index.html`, CSS, JS ou imagens verbatim** para um "clone na íntegra" sem
confirmação de que você detém os direitos (ou a licença). Os arquivos em `raw/` ficam aqui apenas como
**material de análise**, não como base de redistribuição.

---

## 5. O que eu posso fazer a seguir

**A) Clone fiel a partir de artefatos seus** — se você é o titular/licenciado, me envie: `LICENSE.md`
ou comprovante de titularidade, o repositório-fonte, migrations/schema do banco, `docker-compose`,
documentação da API e a config do storage. Com isso eu reconstruo fielmente, inclusive backend, auth
e MinIO. **Não cole segredos/senhas no chat** — use variáveis de ambiente no ambiente de execução.

**B) Reconstrução original (clean-room)** — escrevo do zero um CRM imobiliário com as mesmas
*funcionalidades*, com código e design próprios (sem copiar CSS/JS/imagens do Vivaz), incluindo o que
hoje não existe:
- **Banco:** Postgres + schema derivado do modelo acima (`users`, `members`, `properties`,
  `property_photos`, `contacts`, `leads`, `deals`, `deal_stages`, `tasks`, `documents`, `threads`,
  `messages`, `activity`, `notices`, `settings`);
- **Auth:** sessões/JWT, hash de senha (Argon2id), RBAC por papel, reset de senha, auditoria;
- **Storage:** MinIO/S3-compatible com uploads presigned e URLs assinadas para fotos/plantas/documentos;
- **API + frontend:** REST/OpenAPI e SPA própria com as 7 rotas e os fluxos observados.

**C) Só o levantamento técnico** — paro por aqui com este relatório e as evidências do REA.

---

## 6. Limites que mantive

Apenas GETs passivos de arquivos públicos referenciados. **Não** tentei: acessar banco, buckets ou
painéis admin; burlar autenticação; enumerar diretórios/endpoints; extrair credenciais ou chaves;
executar o bundle em navegador; nem reproduzir código/assets protegidos. Alguns comandos do REA
(captura de runtime, anexação a processos, tráfego) têm efeitos colaterais e só seriam usados com
pedido e autorização explícitos.
