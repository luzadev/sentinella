"""Threshold-based alert evaluation.

For each enabled rule, compares the latest metric value against the threshold.
A rule must stay breached for `duration_seconds` before an Alert is opened
(debounce against transient spikes). When an alert opens and the rule has
auto_remediate, an AI remediation proposal is generated.

evaluate() is synchronous (DB + blocking AI call) and returns a list of
notification events for the async caller to push to Telegram.
"""
import logging
import operator
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, select

from .ai_remediation import propose_remediation
from .models import Action, Alert, AlertRule, AlertStatus, Metric, Server, utcnow

log = logging.getLogger("sentinella.alerts")

OPS = {">": operator.gt, "<": operator.lt, ">=": operator.ge, "<=": operator.le, "==": operator.eq}

# in-memory breach tracking: (server_id, rule_id) -> first breach datetime
_breach_started: dict[tuple[int, int], datetime] = {}


@dataclass
class Notification:
    kind: str               # "alert" | "action" | "resolved"
    alert: Alert
    server_name: str
    action: Action | None = None


def _metric_value(metric: Metric, field: str) -> float | None:
    return getattr(metric, field, None)


def evaluate(session: Session, server: Server, metric: Metric) -> list[Notification]:
    notifications: list[Notification] = []
    rules = session.exec(
        select(AlertRule).where(
            AlertRule.enabled == True,  # noqa: E712
            (AlertRule.server_id == None) | (AlertRule.server_id == server.id),  # noqa: E711
        )
    ).all()

    for rule in rules:
        key = (server.id, rule.id)
        value = _metric_value(metric, rule.metric)
        if value is None:
            continue
        breached = OPS.get(rule.operator, operator.gt)(value, rule.threshold)

        existing = session.exec(
            select(Alert).where(
                Alert.server_id == server.id,
                Alert.rule_id == rule.id,
                Alert.status != AlertStatus.resolved,
            )
        ).first()

        if breached:
            started = _breach_started.setdefault(key, metric.ts)
            held = (metric.ts - started).total_seconds()
            if held >= rule.duration_seconds and not existing:
                alert = Alert(
                    server_id=server.id,
                    rule_id=rule.id,
                    severity=rule.severity,
                    status=AlertStatus.firing,
                    title=f"{rule.name} su {server.name}",
                    message=(
                        f"{rule.metric} = {value:.1f} {rule.operator} {rule.threshold} "
                        f"per oltre {rule.duration_seconds}s"
                    ),
                    value=float(value),
                    breach_started_at=started,
                )
                session.add(alert)
                session.commit()
                session.refresh(alert)
                notifications.append(Notification("alert", alert, server.name))

                if rule.auto_remediate:
                    action = propose_remediation(session, alert)
                    if action:
                        notifications.append(
                            Notification("action", alert, server.name, action=action)
                        )
        else:
            _breach_started.pop(key, None)
            if existing:
                existing.status = AlertStatus.resolved
                existing.resolved_at = utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                notifications.append(Notification("resolved", existing, server.name))

    return notifications


def mark_stale_servers_offline(session: Session, offline_after_seconds: int) -> None:
    now = datetime.now(timezone.utc)
    for server in session.exec(select(Server)).all():
        if server.last_seen is None:
            continue
        last = server.last_seen
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        offline = (now - last).total_seconds() > offline_after_seconds
        new_status = "offline" if offline else "online"
        if server.status != new_status:
            server.status = new_status
            session.add(server)
    session.commit()
