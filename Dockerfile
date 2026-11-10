FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.14-slim@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015 AS lock-tool
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /workspace

FROM lock-tool AS development
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-install-project
ENV PATH="/opt/venv/bin:${PATH}"
