FROM python:3.11.9-slim

ARG RELEASE_IDENTIFIER=unverified
ARG RELEASE_GIT_COMMIT=unverified

LABEL org.opencontainers.image.title="AI Maintenance Copilot" \
      org.opencontainers.image.version="${RELEASE_IDENTIFIER}" \
      org.opencontainers.image.revision="${RELEASE_GIT_COMMIT}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir ".[rag]"

COPY alembic.ini ./
COPY migrations ./migrations

CMD ["python", "-m", "src.operations.worker"]
