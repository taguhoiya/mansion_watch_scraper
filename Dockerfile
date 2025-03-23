FROM python:3.13.1-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# Make the seed script executable
RUN chmod +x seed.py

# Make the entrypoint script executable
RUN chmod +x seed.sh

EXPOSE 8080

ENTRYPOINT ["./seed.sh"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
