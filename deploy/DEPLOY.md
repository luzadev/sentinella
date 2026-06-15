# Deploy in produzione (Virtualmin + systemd + MariaDB)

Guida per installare Sentinella su `sentinella.luzaonline.net`. Richiede accesso **root**.

## Architettura del deploy

```
Internet ──HTTPS──► Apache (Virtualmin, vhost del dominio)
                      │  reverse proxy  /  →  127.0.0.1:8000
                      ▼
              systemd: sentinella.service
              (uvicorn, utente 'sentinella')
                      │
                      ▼
                 MariaDB  (db 'sentinella')
```

Il control plane ascolta **solo su 127.0.0.1**: l'esposizione pubblica e l'SSL
sono gestiti da Apache/Virtualmin. Più sicuro e integrato col pannello.

## 1. Prepara il database in Virtualmin

1. Login Virtualmin → seleziona il dominio `sentinella.luzaonline.net`.
2. **Edit Databases → Create a new database** → nome: `sentinella` (tipo MySQL/MariaDB).
3. L'utente `sentinella` esiste già con la password che hai impostato.
   (Se il nome DB reale è diverso, passalo allo script con `DB_NAME=...`.)

## 2. Clona ed esegui lo script di deploy

```bash
# come root
cd /home/sentinella
git clone https://github.com/luzadev/sentinella.git
cd sentinella
chmod +x deploy/install.sh
sudo APP_USER=sentinella DOMAIN=sentinella.luzaonline.net ./deploy/install.sh
```

Lo script: installa le dipendenze (Python, Node), ti chiede la **password MariaDB**,
genera `control-plane/.env` (con `SECRET_KEY`, password admin ed enroll-token casuali),
builda il frontend, crea il virtualenv, verifica la connessione al DB, installa e
avvia il servizio systemd, e fa un health-check.

➡️ **Annota la password admin e l'enroll-token** stampati alla fine: non verranno più mostrati.

## 3. Reverse proxy + SSL in Virtualmin

1. Abilita i moduli proxy una tantum:
   ```bash
   sudo a2enmod proxy proxy_http headers && sudo systemctl reload apache2
   ```
2. **Virtualmin → dominio → Services → Proxy Paths** → aggiungi
   `Path: /` → `URL: http://127.0.0.1:8000/`.
   (In alternativa, incolla `deploy/apache-proxy.conf` via *Edit Directives*.)
3. **Virtualmin → dominio → SSL Certificate → Let's Encrypt** → richiedi il certificato.

Ora `https://sentinella.luzaonline.net` mostra il pannello di login.

## 4. Configura Telegram e AI (opzionale ma consigliato)

Modifica `control-plane/.env`:
```ini
SENTINELLA_TELEGRAM_BOT_TOKEN=...    # da @BotFather
SENTINELLA_TELEGRAM_CHAT_ID=...      # chat/gruppo dove ricevere gli alert
SENTINELLA_ANTHROPIC_API_KEY=...     # per la remediation AI
SENTINELLA_AI_ENABLED=true
```
Poi: `sudo systemctl restart sentinella`.

> Per ricavare il `chat_id`: scrivi al bot, poi apri
> `https://api.telegram.org/bot<TOKEN>/getUpdates` e leggi `chat.id`.

## 5. Installa un agent (per monitorare un server)

Sullo stesso server o su un altro host Linux:
```bash
cd /opt && sudo git clone https://github.com/luzadev/sentinella.git sentinella-agent
cd sentinella-agent/agent
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp agent.env.example agent.env      # imposta URL + enroll token (vedi sotto)
```
In `agent.env`:
```ini
SENTINELLA_URL=https://sentinella.luzaonline.net
SENTINELLA_ENROLL_TOKEN=<enroll-token generato dallo script>
SENTINELLA_NAME=sentinella-host
SENTINELLA_STATE=/var/lib/sentinella/agent.json
SENTINELLA_SERVICES=apache2,mariadb,sentinella
```
Avvio permanente con systemd:
```bash
sudo cp sentinella-agent.service /etc/systemd/system/
# adatta i percorsi nel file (.service) alla cartella /opt/sentinella-agent/agent
sudo systemctl daemon-reload && sudo systemctl enable --now sentinella-agent
```

## Aggiornamenti

```bash
cd /home/sentinella/sentinella && git pull
sudo ./deploy/install.sh        # rebuild + restart (il .env resta invariato)
```

## Comandi utili

| Azione | Comando |
|---|---|
| Stato servizio | `systemctl status sentinella` |
| Log live | `journalctl -u sentinella -f` |
| Riavvia | `systemctl restart sentinella` |
| Test locale | `curl localhost:8000/api/health` |

## Sicurezza — checklist

- [ ] **Ruota la password MariaDB** (è stata condivisa in chat durante il setup).
- [ ] Verifica che il control plane non sia raggiungibile dall'esterno sulla 8000
      (deve passare solo da Apache/HTTPS). `ss -tlnp | grep 8000` → solo 127.0.0.1.
- [ ] Cambia la password `admin` al primo accesso.
- [ ] L'agent esegue comandi: valuta `sudoers` mirato invece di girare da root.
