#!/usr/bin/env python3
"""Sentinella agent — runs on each managed Linux host.

Responsibilities:
  * enroll once with the control plane (stores a per-host agent token)
  * push system telemetry on every heartbeat
  * execute approved remediation commands and report their result
  * run queued backups (tar.gz of configured paths) and report their result

Config via environment variables (or a .env-style file passed as $1):
  SENTINELLA_URL          e.g. http://control-plane:8000
  SENTINELLA_ENROLL_TOKEN matching the control plane's agent_enroll_token
  SENTINELLA_NAME         friendly server name (default: hostname)
  SENTINELLA_INTERVAL     heartbeat seconds (default 15)
  SENTINELLA_SERVICES     comma-separated systemd units to watch (optional)
  SENTINELLA_TLS_DOMAINS  comma-separated domains[:port] for extra SSL checks (optional)
"""
import json
import os
import platform
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

import httpx
import psutil

# Servizi noti da rilevare automaticamente se presenti sull'host
COMMON_SERVICES = [
    "apache2", "httpd", "nginx", "mariadb", "mysql", "mysqld", "postgresql",
    "redis-server", "redis", "docker", "ssh", "sshd", "cron", "crond",
    "postfix", "dovecot", "named", "bind9", "fail2ban", "ufw", "webmin",
    "php8.1-fpm", "php8.2-fpm", "php8.3-fpm", "php8.4-fpm",
    "sentinella", "sentinella-agent",
]


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def load_env_file(path: str) -> None:
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


class Config:
    def __init__(self):
        self.url = os.environ.get("SENTINELLA_URL", "http://localhost:8000").rstrip("/")
        self.enroll_token = os.environ.get("SENTINELLA_ENROLL_TOKEN", "enroll-change-me")
        self.name = os.environ.get("SENTINELLA_NAME", socket.gethostname())
        self.interval = int(os.environ.get("SENTINELLA_INTERVAL", "15"))
        self.services = [s.strip() for s in os.environ.get("SENTINELLA_SERVICES", "").split(",") if s.strip()]
        self.tls_domains = [s.strip() for s in os.environ.get("SENTINELLA_TLS_DOMAINS", "").split(",") if s.strip()]
        # resolved here (not at import) so an env file passed on the CLI is honored
        self.state_file = Path(os.environ.get("SENTINELLA_STATE", "/var/lib/sentinella/agent.json"))


_public_ip_cache = None


def primary_ip() -> str:
    """IP locale usato per uscire verso l'esterno (nessun pacchetto inviato)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return ""


def all_ipv4() -> list[dict]:
    """Tutti gli IPv4 non-loopback per interfaccia."""
    out = []
    for iface, addrs in psutil.net_if_addrs().items():
        for a in addrs:
            if a.family == socket.AF_INET and not a.address.startswith("127."):
                out.append({"iface": iface, "ip": a.address})
    return out


def public_ip() -> str:
    """IP pubblico, risolto una volta e poi messo in cache."""
    global _public_ip_cache
    if _public_ip_cache is not None:
        return _public_ip_cache
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            _public_ip_cache = httpx.get(url, timeout=5).text.strip()
            if _public_ip_cache:
                return _public_ip_cache
        except Exception:  # noqa: BLE001
            continue
    _public_ip_cache = ""
    return _public_ip_cache


def os_info() -> dict:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "distro": _distro(),
        "python": platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "total_mem_gb": round(psutil.virtual_memory().total / 1e9, 2),
        "ip_local": primary_ip(),
        "ips": all_ipv4(),
        "ip_public": public_ip(),
    }


def _distro() -> str:
    p = Path("/etc/os-release")
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return platform.platform()


def _existing_units() -> set:
    """Unit di servizio realmente installate sull'host (per non riportare unit inesistenti)."""
    try:
        out = subprocess.run(
            ["systemctl", "list-unit-files", "--type=service", "--no-legend", "--plain"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:  # noqa: BLE001
        return set()
    units = set()
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0].endswith(".service"):
            units.add(parts[0][: -len(".service")])
    return units


def detect_services(extra_units: list[str]) -> dict:
    """Stato (active/inactive/failed) dei servizi noti presenti + quelli configurati."""
    existing = _existing_units()
    wanted = list(dict.fromkeys(COMMON_SERVICES + list(extra_units)))  # dedup, ordine stabile
    out = {}
    for unit in wanted:
        if existing and unit not in existing:
            continue
        try:
            r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=8)
            out[unit] = r.stdout.strip() or "unknown"
        except Exception:  # noqa: BLE001
            out[unit] = "unknown"
    return out


def _check_cert(host: str, port: int = 443) -> dict:
    """Handshake TLS: ritorna validità, giorni alla scadenza, emittente."""
    info = {"valid": None, "days_left": None, "not_after": "", "issuer": "", "error": ""}
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                cert = ss.getpeercert()
        info["not_after"] = cert.get("notAfter", "")
        info["days_left"] = int((ssl.cert_time_to_seconds(cert["notAfter"]) - time.time()) // 86400)
        info["issuer"] = dict(x[0] for x in cert.get("issuer", ())).get("organizationName", "")
        info["valid"] = True
    except ssl.SSLCertVerificationError as e:
        info["valid"] = False
        info["error"] = getattr(e, "verify_message", None) or str(e)
        # Solo un certificato scaduto/non ancora valido è "urgente" (days_left=-1 → alert).
        # Hostname mismatch / self-signed / CA non fidata: segnalati ma NON allarmati
        # (days_left resta None, escluso dal calcolo di cert_min_days_left).
        if getattr(e, "verify_code", None) in (10, 9):  # CERT_HAS_EXPIRED / CERT_NOT_YET_VALID
            info["days_left"] = -1
    except Exception as e:  # noqa: BLE001 - host irraggiungibile / no TLS: non è un problema di cert
        info["error"] = str(e)
    return info


# Sottodomini di servizio generati da Virtualmin: non sono siti reali, li escludiamo
_SERVICE_SUBDOMAINS = ("mail.", "webmail.", "admin.", "autoconfig.", "autodiscover.")


def _parse_proxies(txt: str) -> list[dict]:
    """Estrae i reverse proxy da un vhost: ProxyPass e RewriteRule con flag [P]."""
    proxies = []
    for m in re.finditer(r"^\s*ProxyPass\s+(\S+)\s+(\S+)", txt, re.M | re.I):
        path, target = m.group(1), m.group(2)
        if target == "!":  # esclusione (es. ProxyPass /.well-known !), non è un proxy
            continue
        proxies.append({"path": path, "target": target, "kind": "ProxyPass"})
    for m in re.finditer(r"^\s*RewriteRule\s+(\S+)\s+(\S+)\s+\[([^\]]*)\]", txt, re.M | re.I):
        flags = {f.strip().upper() for f in m.group(3).split(",")}
        if "P" in flags:  # [P] = proxy
            proxies.append({"path": m.group(1), "target": m.group(2), "kind": "RewriteRule [P]"})
    return proxies


def _discover_vhosts() -> dict:
    """Domini Apache (ServerName) → porte e reverse proxy configurati. Best-effort, senza root."""
    out: dict[str, dict] = {}
    conf_dirs = ["/etc/apache2/sites-enabled", "/etc/httpd/conf.d", "/etc/apache2/vhosts.d"]
    for d in conf_dirs:
        if not os.path.isdir(d):
            continue
        for f in glob(os.path.join(d, "*.conf")):
            try:
                txt = open(f, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            ports = {int(p) for p in re.findall(r"<VirtualHost[^>]*:(\d+)", txt, re.I)}
            proxies = _parse_proxies(txt)
            for sn in re.findall(r"^\s*ServerName\s+(\S+)", txt, re.M | re.I):
                e = out.setdefault(sn, {"ports": set(), "proxies": []})
                e["ports"].update(ports or {80})
                e["proxies"] = proxies  # stesso file = stesso virtual server (convenzione Virtualmin)
    return out


def virtual_hosts(extra_domains: list[str]) -> list[dict]:
    """Elenco dei virtual host con porte, reverse proxy, stato e certificato SSL."""
    domains = _discover_vhosts()
    for d in extra_domains:
        host, _, p = d.partition(":")
        domains.setdefault(host, {"ports": set(), "proxies": []})["ports"].add(int(p) if p else 443)
    result = []
    for name in sorted(domains):
        if "." not in name or name.startswith("*"):
            continue
        if name.startswith(_SERVICE_SUBDOMAINS):  # mail./webmail./admin. = URL di servizio Virtualmin
            continue
        ports = sorted(domains[name]["ports"])
        entry = {"domain": name, "ports": ports, "active": True,
                 "proxies": domains[name]["proxies"],
                 "ssl_valid": None, "ssl_days_left": None, "ssl_not_after": "", "issuer": "", "error": ""}
        if 443 in ports:
            c = _check_cert(name, 443)
            entry.update(ssl_valid=c["valid"], ssl_days_left=c["days_left"],
                         ssl_not_after=c["not_after"], issuer=c["issuer"], error=c["error"])
        result.append(entry)
    return result


def listening_ports() -> list[dict]:
    """Porte TCP in ascolto, col processo se accessibile."""
    ports: dict[int, str] = {}
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status != psutil.CONN_LISTEN or not c.laddr:
                continue
            name = "?"
            if c.pid:
                try:
                    name = psutil.Process(c.pid).name()
                except Exception:  # noqa: BLE001
                    name = "?"
            if c.laddr.port not in ports or ports[c.laddr.port] == "?":
                ports[c.laddr.port] = name
    except Exception:  # noqa: BLE001
        return []
    return [{"port": p, "process": ports[p]} for p in sorted(ports)]


def top_processes(n: int = 5) -> list[dict]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        procs.append(p.info)
    procs.sort(key=lambda x: (x.get("cpu_percent") or 0), reverse=True)
    return procs[:n]


def collect_metric(cfg: Config) -> dict:
    psutil.cpu_percent(interval=None)  # prime
    time.sleep(0.3)
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    try:
        load1, load5, load15 = os.getloadavg()
    except (OSError, AttributeError):
        load1 = load5 = load15 = 0.0
    per_disk = {}
    for part in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(part.mountpoint)
            per_disk[part.mountpoint] = round(u.percent, 1)
        except (PermissionError, OSError):
            continue
    vhosts = virtual_hosts(cfg.tls_domains)
    cert_days = [v["ssl_days_left"] for v in vhosts if v.get("ssl_days_left") is not None]
    cert_min = float(min(cert_days)) if cert_days else 9999.0
    return {
        "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
        "mem_percent": round(vm.percent, 1),
        "swap_percent": round(sm.percent, 1),
        "disk_percent": round(disk.percent, 1),
        "load1": round(load1, 2), "load5": round(load5, 2), "load15": round(load15, 2),
        "net_sent": net.bytes_sent, "net_recv": net.bytes_recv,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "process_count": len(psutil.pids()),
        "cert_min_days_left": cert_min,
        "extra": {
            "per_disk": per_disk,
            "services": detect_services(cfg.services),
            "vhosts": vhosts,
            "listen_ports": listening_ports(),
            "top_processes": top_processes(),
        },
    }


def enroll(cfg: Config) -> str:
    state_file = cfg.state_file
    if state_file.exists():
        token = json.loads(state_file.read_text()).get("agent_token")
        if token:
            return token
    log(f"Enrollment con {cfg.url} come '{cfg.name}'...")
    r = httpx.post(
        f"{cfg.url}/api/agents/enroll",
        json={"enroll_token": cfg.enroll_token, "name": cfg.name,
              "hostname": socket.gethostname(), "os_info": os_info()},
        timeout=20,
    )
    r.raise_for_status()
    token = r.json()["agent_token"]
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"agent_token": token}))
    log("Enrollment riuscito.")
    return token


def run_command(command: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["/bin/bash", "-c", command], capture_output=True, text=True, timeout=300)
        output = (r.stdout + r.stderr)[-8000:]
        return r.returncode, output
    except subprocess.TimeoutExpired:
        return 124, "Comando andato in timeout (300s)"
    except Exception as e:  # noqa: BLE001
        return 1, f"Errore di esecuzione: {e}"


def run_backup(spec: dict) -> dict:
    """tar.gz the configured paths into dest_dir, apply retention, return result."""
    name = spec.get("name", "backup")
    dest = Path(spec.get("dest_dir", "/var/backups/sentinella"))
    paths = [p for p in spec.get("paths", []) if Path(p).exists()]
    retention = int(spec.get("retention", 7))
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = dest / f"{name}-{stamp}.tar.gz"
    if not paths:
        return {"status": "failed", "output": "Nessun path valido da archiviare", "archive_path": "", "size_bytes": 0}
    cmd = f"tar czf {shlex.quote(str(archive))} " + " ".join(shlex.quote(p) for p in paths)
    code, output = run_command(cmd)
    if code != 0:
        return {"status": "failed", "output": output, "archive_path": "", "size_bytes": 0}
    # retention: keep N most recent archives for this job name
    archives = sorted(dest.glob(f"{name}-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in archives[retention:]:
        try:
            old.unlink()
        except OSError:
            pass
    return {
        "status": "success", "output": output or "ok",
        "archive_path": str(archive), "size_bytes": archive.stat().st_size,
    }


def heartbeat_loop(cfg: Config, token: str) -> None:
    headers = {"X-Agent-Token": token}
    client = httpx.Client(base_url=cfg.url, headers=headers, timeout=30)
    log(f"Heartbeat ogni {cfg.interval}s verso {cfg.url}")
    while True:
        try:
            metric = collect_metric(cfg)
            resp = client.post("/api/agents/heartbeat", json={"metric": metric, "os_info": os_info()})
            resp.raise_for_status()
            data = resp.json()

            for action in data.get("pending_actions", []):
                log(f"Eseguo azione #{action['id']}: {action['command']}")
                code, output = run_command(action["command"])
                client.post(
                    f"/api/agents/actions/{action['id']}/result",
                    json={"status": "done" if code == 0 else "failed",
                          "output": output, "exit_code": code},
                )

            for backup in data.get("pending_backups", []):
                log(f"Eseguo backup run #{backup['run_id']} ({backup.get('name')})")
                result = run_backup(backup)
                client.post("/api/agents/backups/result", json={"run_id": backup["run_id"], **result})

        except httpx.HTTPError as e:
            log(f"Heartbeat errore: {e}")
        time.sleep(cfg.interval)


def main():
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        load_env_file(sys.argv[1])
    cfg = Config()
    token = enroll(cfg)
    heartbeat_loop(cfg, token)


if __name__ == "__main__":
    main()
