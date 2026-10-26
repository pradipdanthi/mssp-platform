FROM python:3.12-slim
WORKDIR /app
RUN apt-get update -y && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
       | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && chmod +x /usr/local/bin/docker \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py edge_config.py enterprise_features.py tenant_isolation.py ngfw_features.py dns_filter.py ransomware_defense.py security_profiles.py ./
COPY static ./static
EXPOSE 9080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9080"]
