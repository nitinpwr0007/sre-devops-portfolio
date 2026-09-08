"""Week 1 demo app — a small Flask service instrumented for SRE labs.

Exposes Prometheus metrics at /metrics so later days can build SLIs:
  - http_requests_total{method,endpoint,status}   -> availability SLI
  - http_request_duration_seconds{endpoint}        -> latency SLI (histogram)

Fault injection (used in Day 6) via environment variables:
  - FAIL_RATE   : probability [0..1] that /api/checkout returns HTTP 500
  - LATENCY_MS  : extra artificial latency added to /api/checkout
"""
import os
import random
import time

from flask import Flask, jsonify, request
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
    return jsonify(service="week1-demo", status="ok")


@app.route("/healthz")
def healthz():
    return jsonify(status="healthy")


@app.route("/api/products")
def products():
    # Fast read path — should almost always be quick and successful.
    time.sleep(random.uniform(0.005, 0.03))
    return jsonify(products=["keyboard", "mouse", "monitor"])


@app.route("/api/checkout", methods=["GET", "POST"])
def checkout():
    # Slower write path — target of fault injection in Day 6.
    time.sleep(random.uniform(0.05, 0.2) + _extra_latency_s())
    if random.random() < _fail_rate():
        return jsonify(error="checkout failed"), 500
    return jsonify(order_id=random.randint(1000, 9999), status="confirmed")


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.before_request
def _start_timer():
    request._start_time = time.perf_counter()


@app.after_request
def _record_metrics(response):
    if request.path == "/metrics":
        return response
    elapsed = time.perf_counter() - getattr(request, "_start_time", time.perf_counter())
    REQUEST_LATENCY.labels(endpoint=request.path).observe(elapsed)
    REQUEST_COUNT.labels(
        method=request.method, endpoint=request.path, status=response.status_code
    ).inc()
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
