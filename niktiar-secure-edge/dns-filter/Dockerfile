FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir pyyaml==6.0.2
COPY categories.yaml feeds.yaml sync_feeds.py ransomware_seed.txt ddns_seed.txt ./
ENV RUNTIME_DIR=/runtime
CMD ["python", "-u", "sync_feeds.py"]
