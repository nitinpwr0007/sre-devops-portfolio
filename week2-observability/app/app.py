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
Day 3 adds OpenTelemetry tracing: spans → OTel Collector → Tempo. The active
trace_id/span_id are also stamped into each JSON log line so Day 4 can jump
trace ↔ logs.
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
from prometheus_client import Counter, Histogram, REGISTRY
from prometheus_client.exposition import choose_encoder

# --- OpenTelemetry tracing (Day 3) ---
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor

app = Flask(__name__)

# TracerProvider exports spans over OTLP/HTTP to the OTel Collector (which forwards
# to Tempo). Endpoint comes from OTEL_EXPORTER_OTLP_ENDPOINT; the SDK appends
# /v1/traces. service.name is how the app shows up in Tempo search.
_resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "week2-app")})
_provider = TracerProvider(resource=_resource)
_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(_provider)
FlaskInstrumentor().instrument_app(app)


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
    # Honor the Accept header so Prometheus can request OpenMetrics and pull
    # exemplars (trace_id) attached to histogram buckets (Day 4).
    encoder, content_type = choose_encoder(request.headers.get("Accept", ""))
    return encoder(REGISTRY), 200, {"Content-Type": content_type}


@app.before_request
def _start_timer():
    g.start_time = time.perf_counter()
    g.request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])


@app.after_request
def _log_and_measure(response):
    if request.path == "/metrics":
        return response
    elapsed = time.perf_counter() - getattr(g, "start_time", time.perf_counter())

    # Grab trace context once; reused for the metric exemplar and the log line.
    span_ctx = trace.get_current_span().get_span_context()
    trace_id = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else None

    # Attach the trace_id as a histogram EXEMPLAR -> metric graph links to the trace.
    exemplar = {"trace_id": trace_id} if trace_id else None
    REQUEST_LATENCY.labels(endpoint=request.path).observe(elapsed, exemplar=exemplar)
    REQUEST_COUNT.labels(
        method=request.method, endpoint=request.path, status=response.status_code
    ).inc()

    # One structured line per request. High-cardinality fields live HERE, not as labels.
    level = logging.ERROR if response.status_code >= 500 else logging.INFO
    fields = {
        "method": request.method,
        "endpoint": request.path,
        "status": response.status_code,
        "duration_ms": round(elapsed * 1000, 1),
        "request_id": getattr(g, "request_id", "-"),
        "remote_addr": request.remote_addr,
    }
    # Stamp the active trace context so Day 4 can pivot logs <-> traces in Grafana.
    if trace_id:
        fields["trace_id"] = trace_id
        fields["span_id"] = format(span_ctx.span_id, "016x")
    log.log(level, "request", extra={"fields": fields})
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
