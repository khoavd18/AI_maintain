FROM python:3.11.9-slim AS core-runtime

ARG RELEASE_IDENTIFIER=unverified
ARG RELEASE_GIT_COMMIT=unverified

LABEL org.opencontainers.image.title="AI Maintenance Copilot" \
      org.opencontainers.image.version="${RELEASE_IDENTIFIER}" \
      org.opencontainers.image.revision="${RELEASE_GIT_COMMIT}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser pyproject.toml README.md ./
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser data_platform ./data_platform
RUN python -m pip install --no-cache-dir "."

COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser migrations ./migrations

USER appuser

CMD ["python", "-m", "src.operations.worker"]


FROM core-runtime AS rag-runtime

ARG TORCH_VERSION=2.12.1

USER root

RUN python -m pip install --no-cache-dir "torch==${TORCH_VERSION}" \
      --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir ".[rag]"

USER appuser
