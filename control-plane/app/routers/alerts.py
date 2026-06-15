from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import get_current_user
from ..database import get_session
from ..models import Alert, AlertRule, AlertStatus, User, utcnow
from ..schemas import AlertRuleIn

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts")
def list_alerts(
    status_filter: str | None = None,
    session: Session = Depends(get_session), _: User = Depends(get_current_user),
):
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(200)
    if status_filter:
        stmt = select(Alert).where(Alert.status == status_filter).order_by(Alert.created_at.desc()).limit(200)
    return session.exec(stmt).all()


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    a = session.get(Alert, alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    a.status = AlertStatus.acknowledged
    session.add(a)
    session.commit()
    return a


# ---- rules CRUD ----

@router.get("/alert-rules")
def list_rules(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return session.exec(select(AlertRule)).all()


@router.post("/alert-rules")
def create_rule(rule: AlertRuleIn, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    obj = AlertRule(**rule.model_dump())
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.put("/alert-rules/{rule_id}")
def update_rule(
    rule_id: int, rule: AlertRuleIn,
    session: Session = Depends(get_session), _: User = Depends(get_current_user),
):
    obj = session.get(AlertRule, rule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Regola non trovata")
    for k, v in rule.model_dump().items():
        setattr(obj, k, v)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@router.delete("/alert-rules/{rule_id}")
def delete_rule(rule_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    obj = session.get(AlertRule, rule_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Regola non trovata")
    session.delete(obj)
    session.commit()
    return {"ok": True}
