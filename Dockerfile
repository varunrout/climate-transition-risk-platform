# Production image for climate-risk pipeline jobs (Azure Container Apps Jobs).
# One image, many jobs: the CLI subcommand (ingest/build-silver/backtest/score/publish/run)
# is passed as the container's command/args -- no per-stage image duplication.

FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv==0.12.5

# Build the venv directly at its final runtime path (/opt/venv) so the
# console-script shebangs uv writes (#!/opt/venv/bin/python) still resolve
# after the COPY into the runtime stage below -- a venv built at a
# different path than it's copied to leaves dangling shebangs.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# --no-dev: production deps only (ruff/mypy/pytest/hypothesis excluded from the runtime image).
# --frozen: fail if uv.lock is out of date rather than silently re-resolving.
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime

# Explicit build/deployment provenance instead of copying .git into the
# image (which we deliberately don't do -- repo history has no reason to
# ship in a production container). Pass the real `git rev-parse HEAD` at
# build time: `docker build --build-arg GIT_SHA=$(git rev-parse HEAD) .`
# climate_risk.contracts.run.resolve_git_sha() reads CLIMATE_RISK_GIT_SHA
# first, before ever attempting a (container-impossible) `git` subprocess
# call. The OCI label is the same value in the standard place image
# tooling/registries look for it (`docker inspect`, GHCR's own UI).
# No default value: an unset build arg must resolve to "genuinely
# unavailable" (empty string -> falsy -> resolve_git_sha() falls through
# to its git-subprocess attempt, which fails cleanly inside a container
# with no .git and returns None) -- never a placeholder string like
# "unknown" that would be mistaken for a real, if unusual, SHA.
ARG GIT_SHA=""
LABEL org.opencontainers.image.revision=${GIT_SHA}

RUN groupadd --gid 1000 climaterisk \
    && useradd --uid 1000 --gid climaterisk --shell /bin/bash --create-home climaterisk

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CLIMATE_RISK_CONFIG_DIR=/app/config \
    CLIMATE_RISK_LAKE_ROOT=/data/lake \
    CLIMATE_RISK_GIT_SHA=${GIT_SHA}

WORKDIR /app
COPY --chown=climaterisk:climaterisk config ./config

RUN mkdir -p /data/lake && chown -R climaterisk:climaterisk /data

USER climaterisk
VOLUME ["/data/lake"]

ENTRYPOINT ["climate-risk"]
CMD ["--help"]
