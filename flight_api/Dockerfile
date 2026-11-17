# Flight REST API image.
# Build from the repository root so requirements.txt is in the build context:
#   docker build -f flight_api/Dockerfile -t travel-agent/flight-api:local .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Run as a non-root user (UID 10001) so a compromised process has no root privileges in the container.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home appuser

WORKDIR /app

# Install pinned dependencies first so this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy this service's code and the shared database code (common/). The service only writes to PostgreSQL,
# so the application files can stay read-only for appuser.
COPY --chown=appuser:appuser common/ ./common/
COPY --chown=appuser:appuser flight_api/ ./flight_api/

USER appuser

EXPOSE 8000

CMD ["uvicorn", "flight_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
