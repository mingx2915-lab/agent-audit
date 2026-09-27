FROM python:3.11-slim

WORKDIR /workspace

COPY apps/api /workspace/apps/api
COPY data /workspace/data

RUN python -m pip install --no-cache-dir -e /workspace/apps/api

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "agent_audit_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
