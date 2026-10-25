FROM python:3.12-slim
WORKDIR /app
# Static docker CLI for caddy reload via docker.sock (no full engine)
RUN apt-get update -y && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
       | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && chmod +x /usr/local/bin/docker \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py config.yaml ./
CMD ["python", "-u", "agent.py"]
