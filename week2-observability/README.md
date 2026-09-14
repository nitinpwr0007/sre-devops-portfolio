# Week 2 — Observability Deep-Dive (LGTM stack)

Mirrors the stack you run at NICE: **L**oki (logs), **G**rafana, **T**empo (traces), **M**imir (metrics).
This week builds it up pillar by pillar. **Day 1 = logs → Loki. Day 2 = metrics → Mimir. Day 3 = traces → Tempo.**

## Stack
| Service | Port | Purpose |
|---|---|---|
| app | http://localhost:8081 | Flask app: **JSON logs** + Prometheus **/metrics** + **OTel traces** |
| Loki | http://localhost:3100 | log store, queried with LogQL |
| Promtail | (internal) | discovers containers via Docker API → ships stdout to Loki |
| Prometheus | http://localhost:9091 | scrapes app metrics, `remote_write`s to Mimir (Day 2) |
| Mimir | http://localhost:9009 | long-term, multi-tenant metric store (Day 2) |
| OTel Collector | (internal) | receives OTLP spans from app → forwards to Tempo (Day 3) |
| Tempo | http://localhost:3200 | trace store, queried with TraceQL (Day 3) |
| Grafana | http://localhost:3001 | Explore for LogQL + PromQL + TraceQL (anonymous Admin) |

## Run
```bash
cd labs/week2-observability
docker compose up -d --build
# generate some traffic
for i in $(seq 1 60); do curl -s -o /dev/null http://localhost:8081/api/checkout; \
  curl -s -o /dev/null http://localhost:8081/api/products; done
```

## See the logs (LogQL)
Grafana → **Explore** → datasource **Loki**. Try:

```logql
# all logs from the app container
{container="week2-demo"}

# parse the JSON, then filter by a field inside the line (high-cardinality — NOT a label)
{container="week2-demo"} | json | status >= 500

# count 5xx lines over time (error-rate style)
sum(count_over_time({container="week2-demo"} | json | status >= 500 [1m]))

# slow requests: duration_ms extracted from the JSON payload
{container="week2-demo"} | json | duration_ms > 300
```

## The one idea that matters: labels vs high-cardinality
- **Labels** (`container`, `stream`, `job`) are the Loki *index*. Keep them **low-cardinality**.
  Never put `request_id`, `duration_ms`, `user_id`, etc. in labels — each unique value spawns a
  new stream and blows up cardinality (the cost/performance problem you manage at NICE).
- **Everything else** lives in the log line as JSON and is extracted at **query time** with `| json`.

Promtail here sets only 3 labels; the app puts `request_id`, `duration_ms`, `remote_addr`,
`method`, `endpoint`, `status` *inside* the JSON line.

## Day 2 — metrics → Mimir (Prometheus `remote_write`)

| Service | Port | Purpose |
|---|---|---|
| Prometheus | http://localhost:9091 | scrapes `app:8080/metrics` every 5s, **`remote_write`s to Mimir** |
| Mimir | http://localhost:9009 | long-term, horizontally-scalable, multi-tenant metric store |
| Grafana | http://localhost:3001 | **Mimir** datasource → PromQL dashboards |

The flow: `app /metrics` → **Prometheus scrape** → **`remote_write`** → **Mimir** → **Grafana (PromQL)**.
Prometheus is just the *collector/shipper* here; Mimir is the *system of record*.

### Why Mimir instead of plain Prometheus?
- **Durable long-term storage** — Prometheus local TSDB is short-retention and node-bound;
  Mimir writes blocks to object storage (S3/GCS; filesystem in this lab) for months/years.
- **Horizontal scale + HA** — Mimir splits distributor/ingester/querier/compactor/store-gateway,
  so ingest and query scale out; a single Prometheus can't.
- **Native multi-tenancy** — every write/read is scoped by an `X-Scope-OrgID` tenant header
  (disabled in this lab → default `anonymous`; **Day 6** turns it on). This is exactly how the
  NICE Mimir serves many teams from one cluster.

### Query the metrics FROM Mimir
Grafana → **Explore** → datasource **Mimir**. Try:
```promql
# request rate by endpoint (RED: Rate)
sum by (endpoint) (rate(http_requests_total{job="week2-app"}[1m]))

# error ratio (RED: Errors)
sum(rate(http_requests_total{job="week2-app",status=~"5.."}[5m]))
  / sum(rate(http_requests_total{job="week2-app"}[5m]))

# p95 latency (RED: Duration) from the histogram
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="week2-app"}[5m])))
```
Or straight from Mimir's Prometheus-compatible API:
```bash
curl -s -G 'http://localhost:9009/prometheus/api/v1/query' \
  --data-urlencode 'query=sum(rate(http_requests_total{job="week2-app"}[1m]))'
```

## Day 3 — traces → Tempo (OpenTelemetry + OTel Collector)

| Piece | Role |
|---|---|
| app (OTel SDK) | `FlaskInstrumentor` creates a **span per request**, exports OTLP/HTTP |
| OTel Collector | central pipeline: receives OTLP → `batch` → forwards to Tempo |
| Tempo | stores trace blocks, serves search/TraceQL on `:3200` |

The flow: `app` → **OTLP/HTTP** → **OTel Collector** → **OTLP/gRPC** → **Tempo** → **Grafana (TraceQL)**.
This app → collector → backend shape is exactly the OpenTelemetry pipeline used at NICE.

### Why a Collector in the middle (not app → Tempo directly)?
- **Decoupling** — apps only know one OTLP endpoint; swap/add backends (Tempo, vendors) without touching app code.
- **Central processing** — batching, resource attributes, redaction, and **tail-sampling** happen once, in the collector.
- **Fan-out** — one pipeline can route traces, metrics, and logs to different stores.

### Trace ↔ logs bridge (sets up Day 4)
Every JSON log line now carries the active `trace_id` and `span_id`:
```json
{"msg":"request","endpoint":"/api/checkout","status":200,"trace_id":"c3b5...","span_id":"6ddc..."}
```
Day 4 uses this to pivot **logs → trace** (and back) inside Grafana.

### See the traces (TraceQL)
Grafana → **Explore** → datasource **Tempo** → **Search** (or TraceQL). Try:
```traceql
{ resource.service.name = "week2-app" }
{ resource.service.name = "week2-app" && duration > 100ms }
{ span.http.status_code = 500 }
```
Or straight from Tempo's API:
```bash
curl -s -G 'http://localhost:3200/api/search' \
  --data-urlencode 'q={ resource.service.name="week2-app" }' --data-urlencode 'limit=5'
```

## Day 4 — correlate trace ↔ logs ↔ metric (the payoff)

The three pillars stop being silos. One request now links across all of them:

| Direction | How it's wired | Where you click |
|---|---|---|
| **log → trace** | Loki `derivedFields` regex-extracts `trace_id` from the JSON line | a log row → **TraceID** button |
| **metric → trace** | app attaches `trace_id` as a histogram **exemplar**; Mimir `exemplarTraceIdDestinations` | a ◇ dot on the latency graph |
| **trace → logs** | Tempo `tracesToLogsV2` custom query `trace_id="${__trace.traceId}"` | a span → **Logs** button |
| **trace → metrics** | Tempo `tracesToMetrics` RED query | a span → **Metrics** button |

### Exemplars: how metric → trace works
1. App serves **OpenMetrics** (`/metrics` honors the `Accept` header) and attaches the active
   `trace_id` to each histogram observation: `REQUEST_LATENCY.observe(elapsed, exemplar={"trace_id": ...})`.
2. Prometheus scrapes exemplars (`--enable-feature=exemplar-storage`) and `remote_write`s them
   (`send_exemplars: true`) to Mimir (`max_global_exemplars_per_user` > 0).
3. Grafana renders exemplar ◇ dots on the latency panel; each links straight to its trace in Tempo.

Verify the exemplar path from the CLI:
```bash
curl -s -G 'http://localhost:9009/prometheus/api/v1/query_exemplars' \
  --data-urlencode 'query=http_request_duration_seconds_bucket{job="week2-app"}' \
  --data-urlencode "start=$(($(date +%s)-600))" --data-urlencode "end=$(date +%s)"
```

### Try the full loop in Grafana
1. **Explore → Loki**: `{container="week2-demo"} | json | status >= 500` → expand a row → click **TraceID**.
2. Lands in **Tempo** on that exact trace → click a span's **Logs** button → back to the same request's logs.
3. **Explore → Mimir**: graph `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))`,
   enable **Exemplars** → click a ◇ dot → opens the slow request's trace.

## Progress
- [x] **D1** — structured JSON logging → Loki, queried with LogQL; labels-vs-cardinality understood
- [x] **D2** — metrics → Mimir via Prometheus `remote_write`; PromQL from Mimir; why Mimir > raw Prometheus
- [x] **D3** — traces → Tempo via OpenTelemetry + OTel Collector; TraceQL; why a collector sits in the middle
- [x] **D4** — correlate trace ↔ logs ↔ metric (derivedFields, tracesToLogs/Metrics, exemplars)
- [ ] D5 — RED + USE dashboards
- [ ] D4 — correlate trace → logs → metric (exemplars)
- [ ] D5 — RED + USE dashboards
- [ ] D6 — multi-tenancy (X-Scope-OrgID) + retention/limits
- [ ] D7 — write-up + capstone

