FROM node:18-alpine AS node-builder

WORKDIR /src

# Copy frontend sources only to leverage Docker layer cache
COPY frontend/package*.json frontend/
COPY frontend/ /src/frontend/
WORKDIR /src/frontend
# Use BuildKit cache for npm to speed subsequent builds
RUN --mount=type=cache,target=/root/.npm \
    npm ci --legacy-peer-deps || npm ci
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps needed for some Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc libssl-dev libffi-dev curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer cache for Python deps
COPY requirements.txt /app/requirements.txt

# Install Python dependencies (use BuildKit pip cache)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

# Copy only application runtime files to keep image small
# - app package, cli scripts, web entrypoint, and config
COPY app/ /app/app/
COPY cli/ /app/cli/
COPY web.py /app/web.py
COPY config.toml /app/config.toml

# Copy built frontend assets from node builder into the static dir expected by the app
COPY --from=node-builder /src/static/dist /app/static/dist

EXPOSE 8000

CMD ["uvicorn", "web:app", "--host", "0.0.0.0", "--port", "8000"]
