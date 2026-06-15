# 🛡️ Sentinella

Sistema di **gestione e monitoraggio per server Linux** con interfaccia di
amministrazione web, alert su Telegram, remediation assistita dall'AI (con
approvazione umana), backup e restore.

Architettura **control plane + agent**: un pannello centrale e un agent leggero
installato su ogni server gestito.

```
┌──────────────┐      heartbeat (metriche)       ┌─────────────────────┐
│   Agent      │ ──────────────────────────────► │                     │
│ (host Linux) │                                  │   Control Plane     │
│              │ ◄── azioni approvate / backup ── │  (FastAPI + SQLite) │
└──────────────┘                                  │                     │
                                                  │  • Dashboard React  │
   ┌──────────┐   alert + approvazioni inline     │  • Alert engine     │
   │ Telegram │ ◄───────────────────────────────► │  • AI remediation   │
   └──────────┘                                   │  • Backup scheduler │
                                                  └─────────────────────┘
```

## Funzionalità

- **Monitoraggio real-time**: CPU, RAM, swap, disco (per mount), load, rete,
  uptime, processi top, stato servizi systemd. Grafici storici nel pannello.
- **Interfaccia di amministrazione** (React): dashboard flotta, dettaglio server,
  alert, regole, remediation, backup. Login con JWT.
- **Alert configurabili**: regole a soglia con durata di sforamento (anti-spike),
  severità info/warning/critical. 5 regole sensate pre-configurate.
- **Notifiche Telegram**: ogni alert arriva in chat; le azioni proposte dall'AI
  hanno bottoni inline **Approva / Rifiuta**.
- **AI remediation con human-in-the-loop**: quando scatta un alert, Claude
  analizza la telemetria e propone **un** comando di fix con livello di rischio.
  **Non viene mai eseguito senza la tua approvazione** (dal pannello o da Telegram).
- **Comandi manuali**: invia comandi ad-hoc a un host dal pannello.
- **Backup & restore**: job pianificati (cron) di `tar.gz` su path configurabili,
  con retention automatica; esecuzione on-demand; storico delle run.

## Struttura

```
control-plane/   Backend FastAPI + frontend buildato (static/)
  app/           API, modelli, alert engine, AI, Telegram, scheduler
agent/           Agent Python da installare sugli host (psutil + httpx)
frontend/        SPA React (Vite + Recharts) — build in control-plane/static
```

## Avvio rapido (sviluppo)

### 1. Control plane
```bash
cd control-plane
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env           # poi modifica i valori (vedi sotto)
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (dev con hot-reload)
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxy API → :8000)
```
Per produzione: `npm run build` → genera `control-plane/static/`, servito
direttamente da FastAPI su `http://localhost:8000`.

### 3. Agent (su ogni server Linux)
```bash
cd agent
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp agent.env.example agent.env    # imposta URL + enroll token
venv/bin/python agent.py agent.env
```
Per renderlo permanente: copia `sentinella-agent.service` in
`/etc/systemd/system/`, adatta i percorsi, poi
`systemctl enable --now sentinella-agent`.

## Configurazione (control-plane/.env)

| Variabile | Descrizione |
|-----------|-------------|
| `SENTINELLA_SECRET_KEY` | Chiave per firmare i JWT — **cambiala** |
| `SENTINELLA_ADMIN_USERNAME/PASSWORD` | Admin creato al primo avvio |
| `SENTINELLA_AGENT_ENROLL_TOKEN` | Token che gli agent usano per registrarsi |
| `SENTINELLA_TELEGRAM_BOT_TOKEN` | Token bot da @BotFather |
| `SENTINELLA_TELEGRAM_CHAT_ID` | Chat/gruppo dove ricevere alert |
| `SENTINELLA_ANTHROPIC_API_KEY` | API key per la remediation AI |
| `SENTINELLA_AI_MODEL` | Default `claude-sonnet-4-6` |
| `SENTINELLA_DATABASE_URL` | SQLite (default) o Postgres |

## Deploy con Docker
```bash
cd frontend && npm install && npm run build && cd ..
cp .env.example control-plane/.env   # configura
docker compose up -d --build
```

## Sicurezza — note importanti

- L'agent **esegue comandi shell** sull'host. Gira con privilegi adeguati: valuta
  un utente dedicato con `sudoers` mirato invece di root.
- La remediation AI è **sempre human-in-the-loop**: nessun comando parte senza
  approvazione esplicita. Il prompt vieta azioni distruttive e classifica il rischio.
- Cambia tutti i token/password di default prima di esporre il servizio.
- Metti il control plane dietro HTTPS (reverse proxy) e limita l'accesso di rete.

## Roadmap (idee per le prossime iterazioni)

- Restore guidato dal pannello (estrazione archivi su path/host scelto)
- Backup off-site (S3/rsync) e verifica integrità
- Metriche persistite con retention/downsampling (TimescaleDB)
- Ruoli utente multipli e audit log
- Autonomia AI graduale ("safe actions" auto-approvate) configurabile per regola
- Notifiche multi-canale (email, Slack, webhook)

---
🤖 Generato con [Claude Code](https://claude.com/claude-code)
