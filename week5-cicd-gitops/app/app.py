"""Week 5 demo app — the thing our CI/CD pipeline builds, tests, scans, ships.

Deliberately tiny: the star of Week 5 is the PIPELINE, not the app. Two routes:
  GET /         -> app name + version (version proves which image is running)
  GET /healthz  -> liveness/readiness probe target for later GitOps deploys
"""
import os

from flask import Flask, jsonify

app = Flask(__name__)

# APP_VERSION is baked into the image at build time (Dockerfile ARG/ENV) so a
# running container can report exactly which build it came from.
APP_VERSION = os.getenv("APP_VERSION", "dev")


@app.get("/")
def home():
    return jsonify(app="week5-cicd", version=APP_VERSION)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
