#!/usr/bin/env bash
# Inicia o VIVAZ na porta 3000.
# Backend automático: usa Supabase se .env estiver configurado; senão SQLite.
# Para forçar: VIVAZ_BACKEND=sqlite|supabase bash rodar.sh
set -e
cd "$(dirname "$0")"
PORT="${PORT:-3000}"
BACKEND="${VIVAZ_BACKEND:-auto}"
if [ "$BACKEND" = "auto" ]; then
  if [ -f .env ] && grep -q '^SUPABASE_SERVICE_ROLE_KEY=' .env; then
    BACKEND="supabase"
  else
    BACKEND="sqlite"
  fi
fi
echo "VIVAZ → porta ${PORT} · backend ${BACKEND} (use o painel Live Preview)"
echo "Login: ${VIVAZ_ADMIN_EMAIL:-admin@vivaz.local} / ${VIVAZ_ADMIN_PASSWORD:-Vivaz@2026}"
if [ "$BACKEND" = "supabase" ]; then
  exec python3 server_supabase.py
fi
exec python3 server.py
