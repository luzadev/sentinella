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
"""
import json
import os
import platform
import shlex
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psutil

STATE_FILE = Path(os.environ.get("SENTINELLA_STATE", "/var/lib/sentinella/agent.json"))


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


def os_info() -> dict:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "distro": _distro(),
        "python": platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "total_mem_gb": round(psutil.virtual_memory().total / 1e9, 2),
    }


def _distro() -> str:
    p = Path("/etc/os-release")
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    return platform.platform()


def service_states(units: list[str]) -> dict:
    out = {}
    for unit in units:
        try:
            r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=10)
            out[unit] = r.stdout.strip() or r.stderr.strip()
        except Exception as e:  # noqa: BLE001
            out[unit] = f"error: {e}"
    return out


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
    return {
        "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
        "mem_percent": round(vm.percent, 1),
        "swap_percent": round(sm.percent, 1),
        "disk_percent": round(disk.percent, 1),
        "load1": round(load1, 2), "load5": round(load5, 2), "load15": round(load15, 2),
        "net_sent": net.bytes_sent, "net_recv": net.bytes_recv,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "process_count": len(psutil.pids()),
        "extra": {
            "per_disk": per_disk,
            "services": service_states(cfg.services),
            "top_processes": top_processes(),
        },
    }


def enroll(cfg: Config) -> str:
    if STATE_FILE.exists():
        token = json.loads(STATE_FILE.read_text()).get("agent_token")
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
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"agent_token": token}))
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
