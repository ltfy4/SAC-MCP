FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY sac_mcp ./sac_mcp

RUN pip install . && \
    useradd -r -u 1001 -m sacmcp && \
    chown -R sacmcp:sacmcp /app
USER sacmcp

ENV MCP_TRANSPORT=http \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=8765
EXPOSE 8765

ENTRYPOINT ["sac-mcp"]
