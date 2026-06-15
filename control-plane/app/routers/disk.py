import os

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_user
from ..database import get_session
from ..models import (Action, ActionStatus, DiskScan, DiskScanStatus, Server,
                      User, utcnow)
from ..schemas import DeletePathIn, DiskScanRequestIn

router = APIRouter(prefix="/api/servers", tags=["disk"])

# Percorsi di sistema che non devono MAI essere cancellati dal pannello.
PROTECTED_PATHS = {
    "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib64", "/proc", "/root",
    "/run", "/sbin", "/sys", "/usr", "/var", "/home", "/opt", "/srv",
}


@router.post("/{server_id}/disk-scan")
def request_scan(
    server_id: int, body: DiskScanRequestIn,
    session: Session = Depends(get_session), _: User = Depends(get_current_user),
):
    if not session.get(Server, server_id):
        raise HTTPException(status_code=404, detail="Server non trovato")
    path = body.path or "/"
    scan = DiskScan(server_id=server_id, path=path, status=DiskScanStatus.pending)
    session.add(scan)
    session.commit()
    session.refresh(scan)
    return scan


@router.get("/{server_id}/disk-scan")
def latest_scan(
    server_id: int,
    session: Session = Depends(get_session), _: User = Depends(get_current_user),
):
    scan = session.exec(
        select(DiskScan).where(DiskScan.server_id == server_id).order_by(DiskScan.created_at.desc()).limit(1)
    ).first()
    return scan


@router.post("/{server_id}/delete-path")
def delete_path(
    server_id: int, body: DeletePathIn,
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
):
    if not session.get(Server, server_id):
        raise HTTPException(status_code=404, detail="Server non trovato")
    path = os.path.normpath(body.path or "")
    if not path or not path.startswith("/") or path in PROTECTED_PATHS:
        raise HTTPException(status_code=400, detail=f"Percorso non consentito: '{path}'")
    # Eliminazione = azione approvata, eseguita dall'agent (che riapplica la denylist)
    action = Action(
        server_id=server_id, kind="delete_path", command=path, risk="high",
        status=ActionStatus.approved, proposed_by_ai=False,
        decided_by=user.username, decided_at=utcnow(),
        ai_reasoning=f"Eliminazione file/cartella richiesta da {user.username}",
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action
