# Slim base keeps the image small (fewer packages = smaller CVE surface for trivy).
FROM python:3.12-slim

# APP_VERSION is passed at build time (--build-arg) and persisted as an env var
# so the running container can report which build it is.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

# Run as a non-root user (defense-in-depth; trivy/k8s flag root containers).
RUN useradd --create-home appuser
USER appuser

EXPOSE 8080
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
