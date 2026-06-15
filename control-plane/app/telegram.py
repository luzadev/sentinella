"""Telegram notifications with inline approve/reject buttons.

Runs a lightweight long-polling loop (getUpdates) in a background task so the
operator can approve or reject AI-proposed remediation actions directly from
the chat. No public webhook required.
"""
import asyncio
import logging

import httpx
from sqlmodel import Session

from .config import settings
from .database import engine
from .models import Action, ActionStatus, utcnow

log = logging.getLogger("sentinella.telegram")
API = "https://api.telegram.org/bot{token}/{method}"


def _enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


async def send_message(text: str, reply_markup: dict | None = None, chat_id: str | None = None) -> None:
    if not _enabled():
        log.info("[telegram disabled] %s", text)
        return
    payload = {
        "chat_id": chat_id or settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    url = API.format(token=settings.telegram_bot_token, method="sendMessage")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            await client.post(url, json=payload)
        except httpx.HTTPError as e:
            log.warning("Telegram send failed: %s", e)


async def send_alert(alert_title: str, message: str, severity: str) -> None:
    icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(severity, "🔔")
    await send_message(f"{icon} <b>{alert_title}</b>\n{message}")


async def send_action_for_approval(action: Action, server_name: str) -> None:
    risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(action.risk, "🟡")
    text = (
        f"🤖 <b>Remediation proposta dall'AI</b>\n"
        f"Server: <b>{server_name}</b>\n"
        f"Rischio: {risk_icon} {action.risk}\n\n"
        f"<b>Diagnosi:</b>\n{action.ai_reasoning}\n\n"
        f"<b>Comando proposto:</b>\n<code>{action.command}</code>\n\n"
        f"Vuoi eseguirlo?"
    )
    markup = {
        "inline_keyboard": [[
            {"text": "✅ Approva ed esegui", "callback_data": f"approve:{action.id}"},
            {"text": "❌ Rifiuta", "callback_data": f"reject:{action.id}"},
        ]]
    }
    await send_message(text, reply_markup=markup)


async def _answer_callback(client: httpx.AsyncClient, callback_id: str, text: str) -> None:
    url = API.format(token=settings.telegram_bot_token, method="answerCallbackQuery")
    await client.post(url, json={"callback_query_id": callback_id, "text": text})


def _apply_decision(action_id: int, approve: bool, who: str) -> tuple[str, str | None]:
    """Returns (human_message, server_name_if_approved)."""
    with Session(engine) as session:
        action = session.get(Action, action_id)
        if not action:
            return "Azione non trovata.", None
        if action.status != ActionStatus.proposed:
            return f"Azione già in stato '{action.status}'.", None
        action.status = ActionStatus.approved if approve else ActionStatus.rejected
        action.decided_at = utcnow()
        action.decided_by = who
        session.add(action)
        session.commit()
        if approve:
            from .models import Server
            srv = session.get(Server, action.server_id)
            return "✅ Approvata — sarà eseguita al prossimo heartbeat dell'agent.", (srv.name if srv else "?")
        return "❌ Rifiutata.", None


async def poll_updates() -> None:
    """Background long-poll loop handling inline-button callbacks."""
    if not _enabled():
        log.info("Telegram polling disabilitato (token/chat_id mancanti).")
        return
    offset = 0
    url = API.format(token=settings.telegram_bot_token, method="getUpdates")
    async with httpx.AsyncClient(timeout=40) as client:
        log.info("Telegram polling avviato.")
        while True:
            try:
                resp = await client.get(url, params={"timeout": 30, "offset": offset})
                data = resp.json()
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    cq = upd.get("callback_query")
                    if not cq:
                        continue
                    who = cq.get("from", {}).get("username") or str(cq.get("from", {}).get("id"))
                    cb_data = cq.get("data", "")
                    if ":" not in cb_data:
                        continue
                    decision, raw_id = cb_data.split(":", 1)
                    if not raw_id.isdigit():
                        continue
                    msg, _ = _apply_decision(int(raw_id), decision == "approve", who)
                    await _answer_callback(client, cq["id"], msg)
                    await send_message(f"{msg} (da @{who})")
            except Exception as e:  # noqa: BLE001 - keep the loop alive
                log.warning("Telegram poll error: %s", e)
                await asyncio.sleep(5)
