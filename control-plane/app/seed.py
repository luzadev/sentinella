"""Seed sensible default alert rules on first run."""
from sqlmodel import Session, select

from .models import AlertRule

DEFAULT_RULES = [
    dict(name="CPU alta", metric="cpu_percent", operator=">", threshold=90,
         duration_seconds=120, severity="warning"),
    dict(name="Memoria critica", metric="mem_percent", operator=">", threshold=92,
         duration_seconds=120, severity="critical"),
    dict(name="Disco quasi pieno", metric="disk_percent", operator=">", threshold=88,
         duration_seconds=60, severity="critical"),
    dict(name="Swap in uso pesante", metric="swap_percent", operator=">", threshold=60,
         duration_seconds=180, severity="warning"),
    dict(name="Load medio elevato", metric="load5", operator=">", threshold=8,
         duration_seconds=180, severity="warning"),
]


def seed_default_rules(session: Session) -> None:
    if session.exec(select(AlertRule)).first():
        return
    for r in DEFAULT_RULES:
        session.add(AlertRule(**r, enabled=True, auto_remediate=True))
    session.commit()
