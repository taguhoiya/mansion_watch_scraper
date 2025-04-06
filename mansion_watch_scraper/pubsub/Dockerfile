FROM --platform=linux/amd64 python:3.11.7-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
  build-essential \
  python3-dev \
  libjpeg-dev \
  zlib1g-dev \
  libpng-dev \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY mansion_watch_scraper/requirements.txt .
RUN pip install --upgrade pip && \
  pip install --no-cache-dir -r requirements.txt

# Copy the project directory maintaining the structure
COPY mansion_watch_scraper /app/mansion_watch_scraper
COPY app /app/app
COPY enums /app/enums
COPY .env.prod /app/.env
COPY service-account.json /app/service-account.json

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV GRPC_DNS_RESOLVER=native
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/service-account.json
ENV PUBSUB_SUBSCRIPTION=mansion-watch-scraper-sub-push
ENV PUBSUB_TOPIC=mansion-watch-scraper-topic
ENV MONGO_URI="mongodb+srv://mansionwatch:mansiondaisuki@mansionwatch.mbt6a.mongodb.net/?retryWrites=true&w=majority&appName=MansionWatch"
ENV MONGO_DATABASE="mansion_watch"

# Expose the port
EXPOSE 8080

# Add proper signal handling
STOPSIGNAL SIGTERM

# Run the HTTP server for push subscription
CMD ["python", "-m", "mansion_watch_scraper.pubsub.health"]
