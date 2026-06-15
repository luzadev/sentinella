#!/usr/bin/env bash
#
# Sentinella — script di deploy del control plane.
# Target: server Linux con systemd + Virtualmin + MariaDB. Eseguire come root.
#
#   sudo APP_USER=sentinella DOMAIN=sentinella.luzaonline.net ./deploy/install.sh
#
# Idempotente: puoi rilanciarlo per aggiornare (fa pull + rebuild + restart).
#
set -euo pipefail

# ---- parametri (override via variabili d'ambiente) ----
APP_USER="${APP_USER:-sentinella}"
DOMAIN="${DOMAIN:-sentinella.luzaonline.net}"
PORT="${PORT:-8000}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-sentinella}"
DB_USER="${DB_USER:-sentinella}"

SERVICE_NAME="sentinella"
log() { printf "\033[1;34m▸ %s\033[0m\n" "$*"; }
err() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; }

[ "$(id -u)" -eq 0 ] || { err "Esegui come root (sudo)."; exit 1; }

APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
[ -n "$APP_HOME" ] || { err "Utente '$APP_USER' inesistente."; exit 1; }

# La repo è quella in cui si trova questo script
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log "Repo: $REPO_DIR  |  utente: $APP_USER  |  dominio: $DOMAIN"

# ---- 1. dipendenze di sistema ----
log "Installo le dipendenze di sistema…"
if command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq git python3 python3-venv python3-dev build-essential curl
  if ! command -v node >/dev/null; then
    log "Installo Node.js 20 (per la build del frontend)…"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
    apt-get install -y -qq nodejs
  fi
elif command -v dnf >/dev/null; then
  dnf install -y -q git python3 python3-devel gcc gcc-c++ make curl
  command -v node >/dev/null || { curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - >/dev/null; dnf install -y -q nodejs; }
else
  err "Package manager non riconosciuto: installa manualmente git, python3-venv, nodejs."; exit 1
fi

# ---- 2. .env del control plane (creato solo se assente) ----
ENV_FILE="$REPO_DIR/control-plane/.env"
if [ ! -f "$ENV_FILE" ]; then
  log "Configuro control-plane/.env"
  read -rsp "Password MariaDB per l'utente '$DB_USER': " DB_PASS; echo
  SECRET="$(openssl rand -hex 32)"
  ADMIN_PASS="$(openssl rand -base64 12)"
  ENROLL="$(openssl rand -hex 16)"
  cat > "$ENV_FILE" <<EOF
SENTINELLA_SECRET_KEY=$SECRET
SENTINELLA_ADMIN_USERNAME=admin
SENTINELLA_ADMIN_PASSWORD=$ADMIN_PASS
SENTINELLA_AGENT_ENROLL_TOKEN=$ENROLL
SENTINELLA_DATABASE_URL=mysql+pymysql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME
SENTINELLA_TELEGRAM_BOT_TOKEN=
SENTINELLA_TELEGRAM_CHAT_ID=
SENTINELLA_ANTHROPIC_API_KEY=
SENTINELLA_AI_MODEL=claude-sonnet-4-6
SENTINELLA_AI_ENABLED=false
SENTINELLA_OFFLINE_AFTER_SECONDS=90
EOF
  GENERATED_ADMIN_PASS="$ADMIN_PASS"
  GENERATED_ENROLL="$ENROLL"
else
  log "control-plane/.env già presente: lo lascio invariato."
fi

# ---- 3. build del frontend ----
log "Build del frontend (Vite → control-plane/static)…"
( cd "$REPO_DIR/frontend" && npm install --no-audit --no-fund --silent && npm run build >/dev/null )

# ---- 4. virtualenv + dipendenze Python ----
log "Creo il virtualenv e installo le dipendenze Python…"
VENV="$REPO_DIR/control-plane/.venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$REPO_DIR/control-plane/requirements.txt"

# ---- 5. permessi ----
chown -R "$APP_USER":"$APP_USER" "$REPO_DIR"

# ---- 6. test connessione MariaDB ----
log "Verifico la connessione al database…"
if ! "$VENV/bin/python" - <<PY
import os, sys
sys.path.insert(0, "$REPO_DIR/control-plane")
os.chdir("$REPO_DIR/control-plane")
from app.config import settings
from sqlalchemy import create_engine, text
try:
    e = create_engine(settings.database_url)
    with e.connect() as c:
        c.execute(text("SELECT 1"))
    print("OK")
except Exception as ex:
    print("FAIL:", ex); sys.exit(1)
PY
then
  err "Connessione al DB fallita. Crea il database '$DB_NAME' e verifica le credenziali nel .env, poi rilancia."
  err "In Virtualmin: Edit Databases → Create a new database → nome '$DB_NAME'."
  exit 1
fi

# ---- 7. servizio systemd ----
log "Installo il servizio systemd '$SERVICE_NAME'…"
sed -e "s|__APP_USER__|$APP_USER|g" \
    -e "s|__APP_DIR__|$REPO_DIR|g" \
    -e "s|__PORT__|$PORT|g" \
    "$REPO_DIR/control-plane/sentinella.service" > "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl restart "$SERVICE_NAME"

# ---- 8. health check ----
sleep 4
if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  log "Control plane ATTIVO su 127.0.0.1:$PORT ✅"
else
  err "Health check fallito. Controlla: journalctl -u $SERVICE_NAME -n 50"
  exit 1
fi

# ---- 9. riepilogo ----
echo
log "Deploy completato."
echo "  • Servizio:   systemctl status $SERVICE_NAME"
echo "  • Log:        journalctl -u $SERVICE_NAME -f"
echo "  • In ascolto: http://127.0.0.1:$PORT  (da esporre via reverse proxy)"
if [ -n "${GENERATED_ADMIN_PASS:-}" ]; then
  echo
  echo "  CREDENZIALI GENERATE (salvale ora, non verranno più mostrate):"
  echo "    admin / $GENERATED_ADMIN_PASS"
  echo "    Enroll token agent: $GENERATED_ENROLL"
fi
echo
echo "  PROSSIMO PASSO — reverse proxy in Virtualmin:"
echo "    Virtualmin → $DOMAIN → Services → Configure Website (o 'Proxy Paths')"
echo "    Aggiungi un proxy:  /  →  http://127.0.0.1:$PORT/"
echo "    Poi abilita SSL (Let's Encrypt) dal pannello. Vedi deploy/DEPLOY.md."
