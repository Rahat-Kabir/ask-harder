from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.config import settings
from app.db.session import new_session
from app.interviews.router import router as interviews_router
from app.interviews.service import recover_orphaned_interviews
from app.methodology import router as methodology_router
from app.skills.router import router as skills_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # background prepare/judge tasks die with the previous process (every
    # deploy restarts the dyno) — release the interviews they left stuck
    async with new_session() as db:
        await recover_orphaned_interviews(db)
    yield


app = FastAPI(title="ask-harder", version="0.1.0", lifespan=lifespan)
# all API routes live under /api: the deployed app serves SPA + API from one
# origin, so page routes (/interviews/123) and JSON routes must not collide.
# /health stays unprefixed — it's for infra probes, not the frontend.
app.include_router(auth_router, prefix="/api")
app.include_router(interviews_router, prefix="/api")
app.include_router(skills_router, prefix="/api")
app.include_router(methodology_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
