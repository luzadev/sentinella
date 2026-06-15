"""AI-driven diagnosis and remediation proposals.

Given a firing alert plus recent host telemetry, ask Claude to produce a
structured remediation proposal (diagnosis + a single concrete shell command +
a risk rating). The proposal is NEVER executed automatically: it is stored as an
Action in 'proposed' state and sent to Telegram for human approval.
"""
import json
import logging

from anthropic import Anthropic
from sqlmodel import Session, select

from .config import settings
from .models import Action, ActionStatus, Alert, Metric, Server

log = logging.getLogger("sentinella.ai")

SYSTEM_PROMPT = """Sei un Site Reliability Engineer esperto di sistemi Linux.
Ricevi un alert e la telemetria recente di un server. Il tuo compito è proporre
UNA singola azione di remediation concreta ed eseguibile per risolvere il problema.

Regole tassative:
- Proponi UN solo comando shell non interattivo, idempotente quando possibile.
- Preferisci sempre l'azione meno distruttiva che risolve il problema.
- NON proporre comandi che cancellano dati utente, formattano dischi, o sono
  irreversibili, a meno che non sia l'unica soluzione: in tal caso risk = "high".
- Classifica il rischio: "low" (restart servizio, pulizia cache/log, reload),
  "medium" (kill processo, pulizia pacchetti, rotazione), "high" (qualsiasi
  cosa che possa causare perdita dati o downtime prolungato).
- Se non c'è un'azione sicura e sensata, restituisci command vuoto e spiega perché.

Rispondi SOLO con JSON valido, nessun altro testo:
{"diagnosis": "...", "command": "...", "kind": "shell|restart_service|cleanup_disk|kill_process", "risk": "low|medium|high"}"""


def _build_context(session: Session, alert: Alert, server: Server) -> str:
    recent = session.exec(
        select(Metric).where(Metric.server_id == server.id).order_by(Metric.ts.desc()).limit(5)
    ).all()
    metrics_view = [
        {
            "ts": m.ts.isoformat(),
            "cpu_percent": m.cpu_percent,
            "mem_percent": m.mem_percent,
            "swap_percent": m.swap_percent,
            "disk_percent": m.disk_percent,
            "load": [m.load1, m.load5, m.load15],
            "process_count": m.process_count,
            "extra": m.extra,
        }
        for m in recent
    ]
    return json.dumps(
        {
            "server": {"name": server.name, "hostname": server.hostname, "os": server.os_info},
            "alert": {
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity,
                "value": alert.value,
            },
            "recent_metrics": metrics_view,
        },
        ensure_ascii=False,
        indent=2,
    )


def propose_remediation(session: Session, alert: Alert) -> Action | None:
    """Create a 'proposed' Action for an alert. Returns it, or None if AI is off/unavailable."""
    if not settings.ai_enabled or not settings.anthropic_api_key:
        log.info("AI remediation disabilitata o API key mancante.")
        return None

    server = session.get(Server, alert.server_id)
    if not server:
        return None

    context = _build_context(session, alert, server)
    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.ai_model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}],
        )
        raw = "".join(block.text for block in resp.content if block.type == "text").strip()
        # tolerate fenced code blocks
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1].removeprefix("json").strip()
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        log.warning("AI remediation fallita: %s", e)
        return None

    command = (data.get("command") or "").strip()
    if not command:
        log.info("L'AI non ha proposto un comando sicuro per alert %s.", alert.id)
        return None

    action = Action(
        server_id=server.id,
        alert_id=alert.id,
        kind=data.get("kind", "shell"),
        command=command,
        risk=data.get("risk", "medium"),
        status=ActionStatus.proposed,
        proposed_by_ai=True,
        ai_reasoning=data.get("diagnosis", ""),
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action
