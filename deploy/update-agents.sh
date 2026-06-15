#!/usr/bin/env bash
#
# Aggiorna TUTTI gli agent Sentinella in un colpo solo: per ogni host fa
# `git pull` del repo dell'agent e riavvia il servizio systemd `sentinella-agent`.
#
# Eseguilo da una macchina che ha accesso SSH a tutti gli host.
# La lista host sta in deploy/agents.txt (una riga per host):
#
#     <ssh_target> <dir_repo_agent>
#     root@web-02            /opt/sentinella-agent
#     sentinella@host.tld    /home/sentinella/sentinella
#
# Righe vuote o che iniziano con # vengono ignorate. Se l'utente remoto non è
# root, lo script usa automaticamente `sudo` per il restart (può chiedere la
# password sul terminale: per questo usa una sessione interattiva con -t).
#
# Nota: aggiorna solo gli AGENT. Per aggiornare il control plane usa
# deploy/install.sh sul server che lo ospita.
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIST="${1:-$SCRIPT_DIR/agents.txt}"

if [ ! -f "$LIST" ]; then
  echo "✗ Lista host non trovata: $LIST"
  echo "  Crea il file copiando l'esempio:  cp $SCRIPT_DIR/agents.txt.example $SCRIPT_DIR/agents.txt"
  exit 1
fi

# Comando eseguito su ogni host. __DIR__ è sostituito con la cartella dell'agent.
# Le $ restano letterali (apici singoli) e vengono valutate sul server.
read -r -d '' REMOTE <<'REMOTE_EOF' || true
  set -e
  cd "__DIR__"
  git pull --ff-only
  if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
  $SUDO systemctl restart sentinella-agent
  sleep 2
  echo "   ✔ commit $(git rev-parse --short HEAD) | agent: $($SUDO systemctl is-active sentinella-agent)"
REMOTE_EOF

ok=0; fail=0
# fd 3 per la lista, così lo stdin (terminale) resta libero per ssh -t / sudo
while read -r target dir _rest <&3; do
  [ -z "${target:-}" ] && continue
  case "$target" in \#*) continue ;; esac
  dir="${dir:-/opt/sentinella-agent}"
  echo "==> $target  ($dir)"
  if ssh -t -o ConnectTimeout=15 "$target" "${REMOTE//__DIR__/$dir}"; then
    ok=$((ok + 1))
  else
    echo "   ✗ ERRORE su $target"
    fail=$((fail + 1))
  fi
  echo
done 3< "$LIST"

echo "── Completato: $ok aggiornati, $fail falliti ──"
[ "$fail" -eq 0 ]
