# Agent image. It also contains BOTH MCP servers.
#
# Why: the MCP servers currently use the stdio transport, which means the agent launches them as
# child processes (sys.executable flight_mcp_server/server.py, ...). A child process must be on the
# same filesystem as its parent, so the servers are packaged into this image. In SP03 they move to
# Streamable HTTP and get their own standalone images/containers.
#
# Build from the repository root:
#   docker build -f agent/Dockerfile -t travel-agent/agent:local .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Run as a non-root user (UID 10001).
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home appuser

WORKDIR /app

# Install pinned dependencies first so this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# agent.py locates the MCP servers relative to the project root (/app), so the folder names must match.
COPY --chown=appuser:appuser agent/ ./agent/
COPY --chown=appuser:appuser flight_mcp_server/ ./flight_mcp_server/
COPY --chown=appuser:appuser hotel_mcp_server/ ./hotel_mcp_server/

USER appuser

# FLIGHT_API_BASE_URL / HOTEL_API_BASE_URL are read from the environment (see docker-compose.yml)
# and forwarded by the agent to the MCP server subprocesses. LLM_PROVIDER should be set at run time.
# This default only lists tools, so it works without the REST APIs or an LLM.
CMD ["python", "agent/agent.py", "What travel tools can you use?"]
