from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_user
from ..database import get_session
from ..models import BackupJob, BackupRun, BackupStatus, Server, User
from ..schemas import BackupJobIn

router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.get("/jobs")
def list_jobs(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return session.exec(select(BackupJob)).all()


@router.post("/jobs")
def create_job(body: BackupJobIn, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    if not session.get(Server, body.server_id):
        raise HTTPException(status_code=404, detail="Server non trovato")
    job = BackupJob(**body.model_dump())
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    job = session.get(BackupJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    session.delete(job)
    session.commit()
    return {"ok": True}


@router.post("/jobs/{job_id}/run")
def run_now(job_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    """Queue a backup run; the agent picks it up on its next heartbeat."""
    job = session.get(BackupJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    run = BackupRun(job_id=job.id, server_id=job.server_id, status=BackupStatus.pending)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.get("/runs")
def list_runs(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return session.exec(select(BackupRun).order_by(BackupRun.started_at.desc()).limit(200)).all()
