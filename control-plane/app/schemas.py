from typing import Optional

from pydantic import BaseModel


# ---- Agent <-> control plane ----

class EnrollRequest(BaseModel):
    enroll_token: str
    name: str
    hostname: str = ""
    os_info: dict = {}


class EnrollResponse(BaseModel):
    server_id: int
    agent_token: str


class MetricIn(BaseModel):
    cpu_percent: float = 0
    mem_percent: float = 0
    swap_percent: float = 0
    disk_percent: float = 0
    load1: float = 0
    load5: float = 0
    load15: float = 0
    net_sent: int = 0
    net_recv: int = 0
    uptime_seconds: int = 0
    process_count: int = 0
    cert_min_days_left: float = 9999
    extra: dict = {}


class HeartbeatRequest(BaseModel):
    metric: MetricIn
    os_info: dict = {}


class CommandOut(BaseModel):
    id: int
    kind: str
    command: str


class DiskScanJob(BaseModel):
    scan_id: int
    path: str


class HeartbeatResponse(BaseModel):
    server_id: int
    pending_actions: list[CommandOut] = []
    pending_backups: list[dict] = []
    pending_disk_scans: list[DiskScanJob] = []


class ActionResultIn(BaseModel):
    status: str            # done | failed
    output: str = ""
    exit_code: Optional[int] = None


class BackupResultIn(BaseModel):
    run_id: int
    status: str            # success | failed
    archive_path: str = ""
    size_bytes: int = 0
    output: str = ""


# ---- Admin UI ----

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AlertRuleIn(BaseModel):
    name: str
    metric: str
    operator: str = ">"
    threshold: float = 90
    duration_seconds: int = 60
    severity: str = "warning"
    enabled: bool = True
    server_id: Optional[int] = None
    auto_remediate: bool = True


class BackupJobIn(BaseModel):
    server_id: int
    name: str
    paths: list[str]
    schedule_cron: str = "0 3 * * *"
    dest_dir: str = "/var/backups/sentinella"
    retention: int = 7
    enabled: bool = True


class ManualActionIn(BaseModel):
    server_id: int
    command: str
    kind: str = "shell"
    risk: str = "medium"


class DiskScanRequestIn(BaseModel):
    path: str = "/"


class DiskScanResultIn(BaseModel):
    scan_id: int
    entries: list = []
    error: str = ""


class DeletePathIn(BaseModel):
    path: str
