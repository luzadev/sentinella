from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_user
from ..database import get_session
from ..models import Metric, Server, User

router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("")
def list_servers(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    servers = session.exec(select(Server)).all()
    out = []
    for s in servers:
        latest = session.exec(
            select(Metric).where(Metric.server_id == s.id).order_by(Metric.ts.desc()).limit(1)
        ).first()
        out.append({
            "id": s.id, "name": s.name, "hostname": s.hostname, "status": s.status,
            "os_info": s.os_info, "tags": s.tags, "last_seen": s.last_seen,
            "latest": {
                "cpu_percent": latest.cpu_percent if latest else None,
                "mem_percent": latest.mem_percent if latest else None,
                "disk_percent": latest.disk_percent if latest else None,
                "load1": latest.load1 if latest else None,
            } if latest else None,
        })
    return out


@router.get("/{server_id}")
def get_server(server_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    s = session.get(Server, server_id)
    if not s:
        raise HTTPException(status_code=404, detail="Server non trovato")
    return s


@router.get("/{server_id}/metrics")
def server_metrics(
    server_id: int, limit: int = 120,
    session: Session = Depends(get_session), _: User = Depends(get_current_user),
):
    rows = session.exec(
        select(Metric).where(Metric.server_id == server_id).order_by(Metric.ts.desc()).limit(limit)
    ).all()
    return list(reversed(rows))


@router.delete("/{server_id}")
def delete_server(server_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    s = session.get(Server, server_id)
    if not s:
        raise HTTPException(status_code=404, detail="Server non trovato")
    session.delete(s)
    session.commit()
    return {"ok": True}
