# Backend image for Heroku (container stack). Heroku's heroku.yml build uses
# the Dockerfile's own directory (backend/) as the build context, so all COPY
# paths here are relative to backend/. Build locally the same way:
#   docker build -t ask-harder-api backend/
FROM python:3.13-slim

# uv: copied from the official distroless image (no pip/curl install needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# copy mode avoids hardlink warnings across layers; bytecode compile trades a
# little build time for faster cold starts
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 1) deps only — this layer is cached unless pyproject/uv.lock change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) app source, then install the project itself into the same venv
COPY . ./
RUN uv sync --frozen --no-dev

# put the venv first on PATH so `uvicorn`/`alembic` resolve without `uv run`
ENV PATH="/app/.venv/bin:$PATH"

# local/dev default; on Heroku $PORT is injected and heroku.yml's run command
# takes over. Shell form so ${PORT:-8000} expands.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
