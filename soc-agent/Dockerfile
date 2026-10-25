FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    SOC_AGENT_PORT=8443 \
    SOC_AGENT_AUDIT_LOG=/var/log/soc-agent/audit.log \
    SOC_AGENT_TRIAGE_AUDIT_LOG=/var/log/soc-agent/triage_audit.log

RUN mkdir -p /var/log/soc-agent /var/lib/soc-agent
EXPOSE 8443
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8443"]
