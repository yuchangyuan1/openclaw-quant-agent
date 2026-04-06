FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY services /app/services
COPY scripts /app/scripts
COPY templates /app/templates
COPY docs /app/docs
COPY openclaw /app/openclaw
COPY README.md /app/README.md
COPY Agent.md /app/Agent.md
COPY project-plan-quant-research.md /app/project-plan-quant-research.md
COPY openclaw-multi-agent-architecture.md /app/openclaw-multi-agent-architecture.md
COPY .env.example /app/.env.example

RUN python -m pip install --upgrade pip && \
    python -m pip install .

CMD ["python", "-m", "uvicorn", "services.planner.main:app", "--host", "0.0.0.0", "--port", "8005"]
