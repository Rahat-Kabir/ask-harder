from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.config import settings
from app.interviews.router import router as interviews_router
from app.methodology import router as methodology_router
from app.skills.router import router as skills_router

app = FastAPI(title="ask-harder", version="0.1.0")
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
