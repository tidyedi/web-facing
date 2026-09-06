# SPDX-License-Identifier: Apache-2.0
# syntax=docker/dockerfile:1

# --- builder: resolve and install into a venv ------------------------------- #
FROM python:3.12-slim AS builder

# git is needed at install time: x12-tidy is pulled from its GitHub repo.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Cache the dependency layer on the lockfile alone.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --no-dev

# --- runtime: just the venv and the app ------------------------------------- #
FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 10001 app
COPY --from=builder --chown=app:app /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

USER app
WORKDIR /home/app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

# 0.0.0.0 so the port is reachable from outside the container.
CMD ["x12-tidy-web", "serve", "--host", "0.0.0.0", "--port", "8000"]
