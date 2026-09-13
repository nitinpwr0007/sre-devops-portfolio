# Week 2 — Observability Deep-Dive (LGTM stack)

Mirrors the stack you run at NICE: **L**oki (logs), **G**rafana, **T**empo (traces), **M**imir (metrics).
This week builds it up pillar by pillar. **Day 1 = logs → Loki + LogQL.**

## Stack (Day 1)
| Service | Port | Purpose |
|---|---|---|
| app | http://localhost:8081 | Flask app, one **JSON log line per request** to stdout |
| Loki | http://localhost:3100 | log store, queried with LogQL |
| Promtail | (internal) | discovers containers via Docker API → ships stdout to Loki |
| Grafana | http://localhost:3001 | Explore view for LogQL (anonymous Admin, no login needed) |

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

## Progress
- [x] **D1** — structured JSON logging → Loki, queried with LogQL; labels-vs-cardinality understood
- [ ] D2 — metrics → Mimir (Prometheus remote_write)
- [ ] D3 — traces → Tempo via OpenTelemetry + OTel Collector / Alloy
- [ ] D4 — correlate trace → logs → metric (exemplars)
- [ ] D5 — RED + USE dashboards
- [ ] D6 — multi-tenancy (X-Scope-OrgID) + retention/limits
- [ ] D7 — write-up + capstone

