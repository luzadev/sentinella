import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session, select

from .. import telegram
from ..alert_engine import evaluate
from ..config import settings
from ..database import get_session
from ..deps import get_agent_server
from ..models import (Action, ActionStatus, BackupRun, BackupStatus, Metric,
                      Server, utcnow)
from ..schemas import (ActionResultIn, BackupResultIn, CommandOut, EnrollRequest,
                       EnrollResponse, HeartbeatRequest, HeartbeatResponse)

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest, session: Session = Depends(get_session)):
    if not secrets.compare_digest(req.enroll_token, settings.agent_enroll_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Enroll token non valido")
    # reuse an existing server with the same name, else create
    server = session.exec(select(Server).where(Server.name == req.name)).first()
    if not server:
        server = Server(name=req.name, agent_token=secrets.token_urlsafe(32))
        session.add(server)
    server.hostname = req.hostname
    server.os_info = req.os_info
    server.status = "online"
    server.last_seen = utcnow()
    session.add(server)
    session.commit()
    session.refresh(server)
    return EnrollResponse(server_id=server.id, agent_token=server.agent_token)


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    req: HeartbeatRequest,
    server: Server = Depends(get_agent_server),
    session: Session = Depends(get_session),
):
    # 1) persist telemetry
    m = req.metric
    metric = Metric(
        server_id=server.id,
        cpu_percent=m.cpu_percent, mem_percent=m.mem_percent, swap_percent=m.swap_percent,
        disk_percent=m.disk_percent, load1=m.load1, load5=m.load5, load15=m.load15,
        net_sent=m.net_sent, net_recv=m.net_recv, uptime_seconds=m.uptime_seconds,
        process_count=m.process_count, cert_min_days_left=m.cert_min_days_left, extra=m.extra,
    )
    server.last_seen = utcnow()
    server.status = "online"
    if req.os_info:
        server.os_info = req.os_info
    session.add(metric)
    session.add(server)
    session.commit()
    session.refresh(metric)

    server_id, metric_id = server.id, metric.id

    # 2) evaluate alert rules off the event loop (blocking AI call inside)
    notifications = await run_in_threadpool(evaluate_in_session, server_id, metric_id)

    # 3) push notifications to Telegram
    for note in notifications:
        if note.kind == "alert":
            await telegram.send_alert(note.alert.title, note.alert.message, note.alert.severity)
        elif note.kind == "action" and note.action is not None:
            await telegram.send_action_for_approval(note.action, note.server_name)
        elif note.kind == "resolved":
            await telegram.send_message(f"✅ <b>Risolto:</b> {note.alert.title}")

    # 4) hand back any approved actions + pending backups for this agent
    pending = session.exec(
        select(Action).where(Action.server_id == server_id, Action.status == ActionStatus.approved)
    ).all()
    actions_out = []
    for a in pending:
        a.status = ActionStatus.running
        a.executed_at = utcnow()
        session.add(a)
        actions_out.append(CommandOut(id=a.id, kind=a.kind, command=a.command))

    backups = session.exec(
        select(BackupRun).where(BackupRun.server_id == server_id, BackupRun.status == BackupStatus.pending)
    ).all()
    backups_out = []
    for b in backups:
        from ..models import BackupJob
        job = session.get(BackupJob, b.job_id)
        b.status = BackupStatus.running
        session.add(b)
        backups_out.append({
            "run_id": b.id,
            "paths": job.paths if job else [],
            "dest_dir": job.dest_dir if job else "/var/backups/sentinella",
            "name": job.name if job else "backup",
            "retention": job.retention if job else 7,
        })
    session.commit()

    return HeartbeatResponse(server_id=server_id, pending_actions=actions_out, pending_backups=backups_out)


@router.post("/actions/{action_id}/result")
def action_result(
    action_id: int,
    res: ActionResultIn,
    server: Server = Depends(get_agent_server),
    session: Session = Depends(get_session),
):
    action = session.get(Action, action_id)
    if not action or action.server_id != server.id:
        raise HTTPException(status_code=404, detail="Azione non trovata")
    action.status = ActionStatus.done if res.status == "done" else ActionStatus.failed
    action.output = res.output
    action.exit_code = res.exit_code
    session.add(action)
    session.commit()
    return {"ok": True}


@router.post("/backups/result")
def backup_result(
    res: BackupResultIn,
    server: Server = Depends(get_agent_server),
    session: Session = Depends(get_session),
):
    run = session.get(BackupRun, res.run_id)
    if not run or run.server_id != server.id:
        raise HTTPException(status_code=404, detail="Backup run non trovato")
    run.status = BackupStatus.success if res.status == "success" else BackupStatus.failed
    run.archive_path = res.archive_path
    run.size_bytes = res.size_bytes
    run.output = res.output
    run.finished_at = utcnow()
    session.add(run)
    session.commit()
    return {"ok": True}


# helper used by run_in_threadpool (kept module-level for clarity)
def evaluate_in_session(server_id: int, metric_id: int):
    from ..database import engine
    with Session(engine) as session:
        srv = session.get(Server, server_id)
        met = session.get(Metric, metric_id)
        return evaluate(session, srv, met)
