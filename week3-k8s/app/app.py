"""Week 3 demo app — cluster anatomy tracer + probe-failure switches.

Day 1: every response reports POD_NAME/POD_IP/NODE_NAME so repeated requests
show the Service load-balancing across replicas.

Day 2: two in-memory switches let us BREAK the probes at runtime and watch
Kubernetes react:
  - POST /toggle/ready   -> /readyz starts returning 503; the failing pod is
                            removed from the Service endpoints (traffic stops).
  - POST /toggle/healthy -> /healthz starts returning 500; the kubelet fails
                            the liveness probe and RESTARTS the container
                            (which resets both switches back to healthy).
"""
import os
import socket

from flask import Flask, jsonify

app = Flask(__name__)

# Downward API (see deployment.yaml) injects these; fall back to hostname.
POD_NAME = os.getenv("POD_NAME", socket.gethostname())
POD_IP = os.getenv("POD_IP", "unknown")
NODE_NAME = os.getenv("NODE_NAME", "unknown")

# In-memory probe switches; reset to healthy whenever the process (re)starts.
STATE = {"ready": True, "healthy": True}


@app.get("/")
def home():
    return jsonify(
        app="week3-k8s",
        msg="hello from Kubernetes",
        pod=POD_NAME,
        pod_ip=POD_IP,
        node=NODE_NAME,
        ready=STATE["ready"],
        healthy=STATE["healthy"],
    )


@app.get("/healthz")
def healthz():
    """Liveness: is the process healthy? 500 makes the kubelet restart it."""
    if STATE["healthy"]:
        return jsonify(status="ok", pod=POD_NAME)
    return jsonify(status="unhealthy", pod=POD_NAME), 500


@app.get("/readyz")
def readyz():
    """Readiness: should this Pod get Service traffic? 503 removes it from endpoints."""
    if STATE["ready"]:
        return jsonify(status="ready", pod=POD_NAME)
    return jsonify(status="notready", pod=POD_NAME), 503


@app.post("/toggle/ready")
def toggle_ready():
    STATE["ready"] = not STATE["ready"]
    return jsonify(pod=POD_NAME, ready=STATE["ready"])


@app.post("/toggle/healthy")
def toggle_healthy():
    STATE["healthy"] = not STATE["healthy"]
    return jsonify(pod=POD_NAME, healthy=STATE["healthy"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
