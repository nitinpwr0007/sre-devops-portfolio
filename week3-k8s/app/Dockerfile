FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

EXPOSE 8080
# single worker so the in-memory readiness/liveness toggle is consistent for the lab
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", "--access-logfile", "-", "app:app"]
