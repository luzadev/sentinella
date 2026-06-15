from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from .database import get_session
from .models import Server


def get_agent_server(
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    session: Session = Depends(get_session),
) -> Server:
    """Authenticate an agent by its per-server token."""
    server = session.exec(select(Server).where(Server.agent_token == x_agent_token)).first()
    if not server:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token agent non valido")
    return server
