FROM python:3.13.1-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["scrapy", "runspider", "mansion_watch_scraper/spiders/mansion_watch_spider.py"]
