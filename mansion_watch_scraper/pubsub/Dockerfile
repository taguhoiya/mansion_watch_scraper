FROM python:3.13.1-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
  build-essential \
  python3-dev \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY mansion_watch_scraper/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the project directory maintaining the structure
COPY mansion_watch_scraper /app/mansion_watch_scraper
COPY app /app/app
COPY enums /app/enums
COPY .env.prod /app/.env

# Create directory for mounted secrets
RUN mkdir -p /app/secrets

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV GRPC_DNS_RESOLVER=native
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/service-account.json

# Add proper signal handling
STOPSIGNAL SIGTERM

# Run both the Pub/Sub subscriber and health check server
CMD ["sh", "-c", "python -m mansion_watch_scraper.pubsub.service & python -m mansion_watch_scraper.pubsub.health"]
