from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_user
from ..database import get_session
from ..models import Action, ActionStatus, Server, User, utcnow
from ..schemas import ManualActionIn

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("")
def list_actions(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return session.exec(select(Action).order_by(Action.created_at.desc()).limit(200)).all()


@router.post("/{action_id}/approve")
def approve(action_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    a = session.get(Action, action_id)
    if not a:
        raise HTTPException(status_code=404, detail="Azione non trovata")
    if a.status != ActionStatus.proposed:
        raise HTTPException(status_code=409, detail=f"Azione in stato '{a.status}'")
    a.status = ActionStatus.approved
    a.decided_at = utcnow()
    a.decided_by = user.username
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


@router.post("/{action_id}/reject")
def reject(action_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    a = session.get(Action, action_id)
    if not a:
        raise HTTPException(status_code=404, detail="Azione non trovata")
    a.status = ActionStatus.rejected
    a.decided_at = utcnow()
    a.decided_by = user.username
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


@router.post("")
def create_manual_action(
    body: ManualActionIn, user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    """Operator-issued command. Created already-approved, queued for the agent."""
    if not session.get(Server, body.server_id):
        raise HTTPException(status_code=404, detail="Server non trovato")
    a = Action(
        server_id=body.server_id, command=body.command, kind=body.kind, risk=body.risk,
        status=ActionStatus.approved, proposed_by_ai=False,
        decided_by=user.username, decided_at=utcnow(),
        ai_reasoning="Comando manuale dell'operatore",
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a
