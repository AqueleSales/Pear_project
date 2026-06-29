FROM python:3.11-slim

WORKDIR /app

# Dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App files
COPY nomad_api.py .
COPY world_manager.py .

# Create data dir
RUN mkdir -p /data && chmod 777 /data

# Non-root user
RUN useradd -m -u 1000 nomad
USER nomad

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/api/health')"

# Expose
EXPOSE 5000

# Run
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "nomad_api:app"]
