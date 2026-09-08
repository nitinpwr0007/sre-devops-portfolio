FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

EXPOSE 8080
# 2 workers so latency in one request doesn't block metric scrapes.
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
