# ═══════════════════════════════════════════════════════════════════════════
# Stage 1: Build Vue frontend
# ═══════════════════════════════════════════════════════════════════════════

FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

# Copy package files first for caching
COPY deep-research-agent/frontend/package.json deep-research-agent/frontend/package-lock.json ./
RUN npm ci

# Copy frontend source
COPY deep-research-agent/frontend/ ./

# Build
RUN npm run build

# ═══════════════════════════════════════════════════════════════════════════
# Stage 2: Python backend
# ═══════════════════════════════════════════════════════════════════════════

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash \
    && rm -rf /var/lib/apt/lists/*

# Copy Python project
COPY pyproject.toml research-context.md ./
COPY src ./src

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install ".[postgres]"

# Copy built frontend from Stage 1
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Create data directories
RUN mkdir -p /app/.local /app/.local/reports

ENTRYPOINT []
CMD ["deep-research-agent-web", "--host", "0.0.0.0", "--port", "8000"]
