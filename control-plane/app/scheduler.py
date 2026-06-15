"""Background scheduler: marks stale servers offline and queues due backups."""
import logging
from datetime import datetime, timedelta, timezone

from croniter import croniter
from sqlmodel import Session, select

from .alert_engine import mark_stale_servers_offline
from .config import settings
from .database import engine
from .models import BackupJob, BackupRun, BackupStatus

log = logging.getLogger("sentinella.scheduler")


def check_offline_servers():
    with Session(engine) as session:
        mark_stale_servers_offline(session, settings.offline_after_seconds)


def queue_due_backups():
    """Queue a BackupRun for any enabled job whose cron slot fell in the last minute."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=60)
    with Session(engine) as session:
        for job in session.exec(select(BackupJob).where(BackupJob.enabled == True)).all():  # noqa: E712
            try:
                prev = croniter(job.schedule_cron, now).get_prev(datetime)
            except (ValueError, KeyError):
                log.warning("Cron non valido per job %s: %s", job.id, job.schedule_cron)
                continue
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            if prev < window_start:
                continue
            # avoid duplicate pending/running run for this job
            already = session.exec(
                select(BackupRun).where(
                    BackupRun.job_id == job.id,
                    BackupRun.status.in_([BackupStatus.pending, BackupStatus.running]),
                )
            ).first()
            if already:
                continue
            session.add(BackupRun(job_id=job.id, server_id=job.server_id, status=BackupStatus.pending))
            log.info("Backup schedulato per job %s (%s)", job.id, job.name)
        session.commit()
