import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from . import telegram
from .auth import ensure_bootstrap_admin
from .database import engine, init_db
from .routers import actions, agents, alerts, auth, backups, disk, servers
from .scheduler import check_offline_servers, queue_due_backups
from .seed import seed_default_rules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sentinella")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        ensure_bootstrap_admin(session)
        seed_default_rules(session)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_offline_servers, "interval", seconds=30, id="offline")
    scheduler.add_job(queue_due_backups, "interval", seconds=60, id="backups")
    scheduler.start()

    tg_task = asyncio.create_task(telegram.poll_updates())
    log.info("Sentinella control plane avviato.")
    try:
        yield
    finally:
        tg_task.cancel()
        scheduler.shutdown(wait=False)


app = FastAPI(title="Sentinella", description="Gestione e monitoraggio server Linux", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, agents.router, servers.router, alerts.router, actions.router, backups.router, disk.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "sentinella"}


# Serve the built React frontend if present (control-plane/static)
_static = Path(__file__).resolve().parent.parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="static")
