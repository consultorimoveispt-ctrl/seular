#!/usr/bin/env bash
# Publica via SSH Deploy Key (não depende de escopo de PAT).
# 1) cat ~/.ssh/vivaz_deploy.pub  →  GitHub → seular → Settings →
#    Deploy keys → Add deploy key → marque "Allow write access"
# 2) ./publicar-ssh.sh
set -euo pipefail
cd "$(dirname "$0")"

KEY="${VIVAZ_DEPLOY_KEY:-$HOME/.ssh/vivaz_deploy}"
REMOTE="${VIVAZ_SSH_REMOTE:-git@github.com:consultorimoveispt-ctrl/seular.git}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [ ! -f "$KEY" ]; then
  echo "Chave não encontrada em $KEY" >&2
  echo "Gere com: ssh-keygen -t ed25519 -C vivaz-deploy -f $KEY -N ''" >&2
  exit 1
fi

if git remote get-url ssh-origin >/dev/null 2>&1; then
  git remote set-url ssh-origin "$REMOTE"
else
  git remote add ssh-origin "$REMOTE"
fi

echo "Enviando $BRANCH → $REMOTE"
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
  git push -u ssh-origin "$BRANCH"

echo "✓ Publicado por SSH."
