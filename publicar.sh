#!/usr/bin/env bash
# Publica o VIVAZ no GitHub. O token NÃO é gravado em nenhum arquivo:
# é enviado apenas como header HTTP durante este push.
#
#   GITHUB_TOKEN=seu_token ./publicar.sh
#
# Token: GitHub → Settings → Developer settings → Personal access tokens
#        → Fine-grained tokens → Contents: read AND write + Workflows: read AND
#        write (o repo contém .github/workflows/ci.yml), neste repo apenas.
#        Ou um classic PAT com escopo `repo`.
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "Defina GITHUB_TOKEN antes de rodar:" >&2
  echo "  GITHUB_TOKEN=seu_token ./publicar.sh" >&2
  exit 1
fi

REMOTE="${VIVAZ_REMOTE:-https://github.com/consultorimoveispt-ctrl/seular.git}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE"
else
  git remote add origin "$REMOTE"
fi

# Git over HTTPS no GitHub usa Basic auth (Bearer só funciona na API REST).
# Usuário "x-access-token" + PAT como senha, codificado só em memória.
AUTH="$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\n')"

echo "Enviando $BRANCH → $REMOTE"
git -c "http.extraheader=AUTHORIZATION: basic ${AUTH}" \
    push -u origin "$BRANCH"

echo "✓ Publicado. O token não foi salvo no repositório nem no remote."
git remote -v
