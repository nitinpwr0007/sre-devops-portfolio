"""Week 2 demo app — instrumented for the LGTM stack.

Day 1 focus: structured JSON logging → Loki.
Each request emits ONE JSON log line to stdout. Promtail ships stdout to Loki,
and we query it with LogQL in Grafana.

Design rule you enforce at NICE (labels vs high-cardinality):
  - LOW-cardinality fields (method, endpoint, status) are safe as Loki *labels*.
  - HIGH-cardinality fields (request_id, duration_ms, remote_addr) stay INSIDE the
    JSON log line and are extracted at query time with `| json` — never as labels.
Promtail here only sets a couple of low-card labels; everything else is log content.

Metrics (Prometheus) are kept so Day 2 can wire metrics → Mimir.
Fault injection via env: FAIL_RATE (0..1 of /api/checkout → 500), LATENCY_MS.
"""
import json
import logging
import os
import random
import sys
import time
import uuid

from flask import Flask, g, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


class JsonFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object for Loki."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge any structured fields attached via logger.*(..., extra={"fields": {...}})
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(fields)
        return json.dumps(payload)


def _setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    return logging.getLogger("week2-demo")


log = _setup_logging()


def _fail_rate() -> float:
    try:
        return float(os.getenv("FAIL_RATE", "0"))
    except ValueError:
        return 0.0


def _extra_latency_s() -> float:
    try:
        return float(os.getenv("LATENCY_MS", "0")) / 1000.0
    except ValueError:
        return 0.0


@app.route("/")
def index():
    return jsonify(service="week2-demo", status="ok")


@app.route("/healthz")
def healthz():
    return jsonify(status="healthy")


@app.route("/api/products")
def products():
    time.sleep(random.uniform(0.005, 0.03))
    return jsonify(products=["keyboard", "mouse", "monitor"])


@app.route("/api/checkout", methods=["GET", "POST"])
def checkout():
    time.sleep(random.uniform(0.05, 0.2) + _extra_latency_s())
    if random.random() < _fail_rate():
        return jsonify(error="checkout failed"), 500
    return jsonify(order_id=random.randint(1000, 9999), status="confirmed")


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.before_request
def _start_timer():
    g.start_time = time.perf_counter()
    g.request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])


@app.after_request
def _log_and_measure(response):
    if request.path == "/metrics":
        return response
    elapsed = time.perf_counter() - getattr(g, "start_time", time.perf_counter())
    REQUEST_LATENCY.labels(endpoint=request.path).observe(elapsed)
    REQUEST_COUNT.labels(
        method=request.method, endpoint=request.path, status=response.status_code
    ).inc()

    # One structured line per request. High-cardinality fields live HERE, not as labels.
    level = logging.ERROR if response.status_code >= 500 else logging.INFO
    log.log(
        level,
        "request",
        extra={
            "fields": {
                "method": request.method,
                "endpoint": request.path,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 1),
                "request_id": getattr(g, "request_id", "-"),
                "remote_addr": request.remote_addr,
            }
        },
    )
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
