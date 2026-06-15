from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger
from sqlmodel import Field, SQLModel, Column, JSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Enums ----------

class Severity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(str, Enum):
    firing = "firing"
    acknowledged = "acknowledged"
    resolved = "resolved"


class ActionStatus(str, Enum):
    proposed = "proposed"      # AI proposed, waiting for human approval
    approved = "approved"      # approved, queued for the agent
    rejected = "rejected"      # human rejected
    running = "running"        # agent is executing
    done = "done"
    failed = "failed"


class BackupStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class DiskScanStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


# ---------- Tables ----------

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    role: str = "admin"
    created_at: datetime = Field(default_factory=utcnow)


class Server(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    hostname: str = ""
    agent_token: str = Field(index=True)
    status: str = "unknown"           # online | offline | unknown
    os_info: dict = Field(default_factory=dict, sa_column=Column(JSON))
    tags: list = Field(default_factory=list, sa_column=Column(JSON))
    last_seen: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class Metric(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    server_id: int = Field(index=True, foreign_key="server.id")
    ts: datetime = Field(default_factory=utcnow, index=True)
    cpu_percent: float = 0
    mem_percent: float = 0
    swap_percent: float = 0
    disk_percent: float = 0
    load1: float = 0
    load5: float = 0
    load15: float = 0
    net_sent: int = Field(default=0, sa_type=BigInteger)
    net_recv: int = Field(default=0, sa_type=BigInteger)
    uptime_seconds: int = Field(default=0, sa_type=BigInteger)
    process_count: int = 0
    # giorni mancanti alla scadenza del certificato SSL più "vicino" (9999 = nessun cert)
    cert_min_days_left: float = 9999
    # per-disk usage, top processes, service states, certificati, porte, ecc.
    extra: dict = Field(default_factory=dict, sa_column=Column(JSON))


class AlertRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    metric: str                       # cpu_percent | mem_percent | disk_percent | load1 ...
    operator: str = ">"               # > | < | >= | <= | ==
    threshold: float = 90
    duration_seconds: int = 60        # must breach for at least this long
    severity: str = Severity.warning
    enabled: bool = True
    # optional scoping; empty = applies to all servers
    server_id: Optional[int] = Field(default=None, foreign_key="server.id")
    auto_remediate: bool = True       # ask the AI to propose a fix when this fires


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    server_id: int = Field(index=True, foreign_key="server.id")
    rule_id: Optional[int] = Field(default=None, foreign_key="alertrule.id")
    severity: str = Severity.warning
    status: str = AlertStatus.firing
    title: str = ""
    message: str = ""
    value: float = 0
    created_at: datetime = Field(default_factory=utcnow, index=True)
    resolved_at: Optional[datetime] = None
    breach_started_at: Optional[datetime] = None


class Action(SQLModel, table=True):
    """A remediation action: proposed by the AI, approved by a human, run by the agent."""
    id: Optional[int] = Field(default=None, primary_key=True)
    server_id: int = Field(index=True, foreign_key="server.id")
    alert_id: Optional[int] = Field(default=None, foreign_key="alert.id")
    kind: str = "shell"               # shell | restart_service | cleanup_disk | kill_process
    command: str = ""                 # the concrete command to run on the host
    risk: str = "medium"              # low | medium | high
    status: str = ActionStatus.proposed
    proposed_by_ai: bool = False
    ai_reasoning: str = ""
    output: str = ""
    exit_code: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
    decided_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    decided_by: str = ""


class BackupJob(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    server_id: int = Field(index=True, foreign_key="server.id")
    name: str
    paths: list = Field(default_factory=list, sa_column=Column(JSON))   # dirs/files to back up
    schedule_cron: str = "0 3 * * *"  # default 03:00 daily
    dest_dir: str = "/var/backups/sentinella"
    retention: int = 7                # keep N most recent
    enabled: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class BackupRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True, foreign_key="backupjob.id")
    server_id: int = Field(index=True, foreign_key="server.id")
    status: str = BackupStatus.pending
    archive_path: str = ""
    size_bytes: int = 0
    output: str = ""
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None


class DiskScan(SQLModel, table=True):
    """On-demand disk usage analysis of a path on a host (immediate children, sorted by size)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    server_id: int = Field(index=True, foreign_key="server.id")
    path: str = "/"
    status: str = DiskScanStatus.pending
    # [{path, name, size_bytes, is_dir}] ordinato per size desc
    entries: list = Field(default_factory=list, sa_column=Column(JSON))
    error: str = ""
    created_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: Optional[datetime] = None
