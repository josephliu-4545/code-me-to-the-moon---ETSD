# syntax=docker/dockerfile:1
#
# Earth System Trend Detective: one container, one origin.
# FastAPI serves the API at /api/* and the built React app at /app/.
# Build:  docker build -t estd .
# Run:    docker run --rm -p 8080:8080 -e EE_PROJECT_ID=... estd   then open http://127.0.0.1:8080/app/
# No credentials are built into the image: configure Earth Engine at run time (see DEPLOYMENT.md).

# ---- Stage 1: build the frontend -------------------------------------------------------------
FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Assets are served under /app/; API calls stay same-origin (/api/...), so VITE_API_BASE stays empty.
ENV VITE_BASE=/app/
RUN npm run build

# ---- Stage 2: runtime ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/backend
# Exact versions (resolved from requirements.txt for Python 3.12 / Linux).
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock

RUN useradd --system --uid 10001 --create-home --home-dir /home/estd --shell /usr/sbin/nologin estd
COPY backend/app ./app
COPY --from=frontend /src/frontend/dist /srv/frontend

ENV FRONTEND_DIST_DIR=/srv/frontend \
    PORT=8080
USER 10001
EXPOSE 8080

# One worker: caches, in-flight request sharing, the rate limiter and the Nominatim throttle are per process.
# --no-proxy-headers: client identity is decided only by the app's trusted-proxy rules (TRUSTED_PROXY_IPS).
# No --reload and no development tooling in this image.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 1 --no-proxy-headers --no-server-header"]
